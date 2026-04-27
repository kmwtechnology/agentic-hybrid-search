/**
 * PipelineSummaryCard
 *
 * Renders the end-of-pipeline retrieval-quality summary emitted as
 * `PipelineSummaryEvent`. Two layouts:
 *
 *  - Ground-truth: BM25 → Hybrid → Reranked metric progression with
 *    NDCG@10 / MRR / Recall@20 / Precision@10. Latency cost-benefit
 *    table at the bottom.
 *  - Fallback: self-referential confidence proxy (top-1 reranker score,
 *    score gap, score variance, rank-change count) plus the same
 *    latency table without lift numbers.
 *
 * The card is silent when no PipelineSummaryEvent has been received
 * (e.g. pipeline still running, summary intent, or first load).
 */

import { useState } from 'react'
import { useObservabilityStore } from '../../stores/observabilityStore'
import type {
  ConfidenceLabel,
  GenerationJudgment,
  GenerationVerdict,
  LatencyStage,
  PipelineSummaryEvent,
  StageMetrics,
} from '../../types/events'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(n: number | null | undefined, digits = 3): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return n.toFixed(digits)
}

function fmtMs(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return `${Math.round(n)}ms`
}

function fmtLift(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  if (n > 0) return `+${fmt(n, 3)}`
  return fmt(n, 3)
}

const STAGE_LABEL: Record<LatencyStage['stage'], string> = {
  stock_bm25: 'Stock BM25',
  bm25: 'Your BM25',
  hybrid: 'Hybrid (vec+BM25)',
  reranked: 'Reranked',
}

// Subset of optimization keys that reshape the BM25 multi_match query.
// When any of these are off, "Your BM25" reflects a degraded build vs Stock.
const BM25_TUNING_KEYS = ['fuzzy', 'synonyms', 'phonetic', 'phrase_boost', 'field_boost'] as const

const VERDICT_TONE: Record<GenerationVerdict, { chip: string; label: string }> = {
  llm_better: {
    chip: 'bg-emerald-900/40 text-emerald-200 border-emerald-700/50',
    label: 'LLM judged BETTER',
  },
  tied: {
    chip: 'bg-gray-800/60 text-gray-200 border-gray-600',
    label: 'Tied',
  },
  llm_worse: {
    chip: 'bg-rose-900/40 text-rose-200 border-rose-700/50',
    label: 'LLM judged WORSE',
  },
}

const CONFIDENCE_TONE: Record<ConfidenceLabel, { dot: string; chip: string; text: string }> = {
  high: {
    dot: 'bg-emerald-400',
    chip: 'bg-emerald-900/40 text-emerald-200 border-emerald-700/50',
    text: 'text-emerald-200',
  },
  medium: {
    dot: 'bg-amber-400',
    chip: 'bg-amber-900/40 text-amber-200 border-amber-700/50',
    text: 'text-amber-200',
  },
  low: {
    dot: 'bg-rose-400',
    chip: 'bg-rose-900/40 text-rose-200 border-rose-700/50',
    text: 'text-rose-200',
  },
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MetricCell({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex flex-col gap-0.5 text-center">
      <span className="text-[11px] uppercase tracking-wide text-gray-400">{label}</span>
      <span className="font-mono text-sm text-gray-100" title={hint}>
        {value}
      </span>
    </div>
  )
}

function StageRow({
  name,
  stage,
  badge,
}: {
  name: string
  stage: StageMetrics | null | undefined
  badge?: React.ReactNode
}) {
  if (!stage) return null
  return (
    <div className="grid grid-cols-[8rem_repeat(4,1fr)_auto] items-center gap-3 px-3 py-2 rounded-md bg-gray-800/40 border border-gray-700/50">
      <span className="text-sm text-gray-100 font-medium flex items-center gap-1.5">
        {name}
        {badge}
      </span>
      <MetricCell label="NDCG@10" value={fmt(stage.ndcg10, 3)} />
      <MetricCell label="MRR" value={fmt(stage.mrr, 3)} />
      <MetricCell label="Recall@20" value={fmt(stage.recall20, 3)} />
      <MetricCell label="P@10" value={fmt(stage.precision10, 3)} />
      <span
        className="text-[10px] uppercase tracking-wide text-gray-500"
        title={`${stage.judged_count} of the returned items had a ground-truth ESCI judgment`}
      >
        {stage.judged_count}/10 judged
      </span>
    </div>
  )
}

function LatencyTable({ rows }: { rows: LatencyStage[] }) {
  const hasGroundTruth = rows.some((r) => r.ndcg !== null && r.ndcg !== undefined)
  return (
    <div className="space-y-1">
      <div className="text-[11px] uppercase tracking-wide text-gray-400 px-1">
        Latency cost-benefit
      </div>
      <div className="rounded-md border border-gray-700/50 overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-gray-800/60 text-gray-400">
            <tr>
              <th className="text-left px-3 py-1.5 font-normal">Stage</th>
              <th className="text-right px-3 py-1.5 font-normal">Latency</th>
              {hasGroundTruth && (
                <>
                  <th className="text-right px-3 py-1.5 font-normal">NDCG</th>
                  <th
                    className="text-right px-3 py-1.5 font-normal"
                    title="Marginal NDCG lift per 100ms vs the previous stage"
                  >
                    Lift / 100ms
                  </th>
                </>
              )}
            </tr>
          </thead>
          <tbody className="bg-gray-900/40">
            {rows.map((row) => (
              <tr key={row.stage} className="border-t border-gray-700/40">
                <td className="px-3 py-1.5 text-gray-200">{STAGE_LABEL[row.stage]}</td>
                <td className="px-3 py-1.5 text-right font-mono text-gray-300">
                  {fmtMs(row.latency_ms)}
                </td>
                {hasGroundTruth && (
                  <>
                    <td className="px-3 py-1.5 text-right font-mono text-gray-300">
                      {fmt(row.ndcg, 3)}
                    </td>
                    <td
                      className={`px-3 py-1.5 text-right font-mono ${
                        row.ndcg_lift_per_100ms !== null &&
                        row.ndcg_lift_per_100ms !== undefined &&
                        row.ndcg_lift_per_100ms > 0
                          ? 'text-emerald-300'
                          : row.ndcg_lift_per_100ms !== null &&
                              row.ndcg_lift_per_100ms !== undefined &&
                              row.ndcg_lift_per_100ms < 0
                            ? 'text-rose-300'
                            : 'text-gray-400'
                      }`}
                    >
                      {fmtLift(row.ndcg_lift_per_100ms)}
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export function PipelineSummaryCard() {
  const summary = useObservabilityStore((s) => s.pipelineSummary)
  const [expanded, setExpanded] = useState(true)

  if (!summary) return null

  return (
    <div className="px-4 pb-4">
      <div className="rounded-lg border border-gray-700 bg-gray-900/60">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center justify-between w-full px-4 py-3 text-left"
          aria-expanded={expanded}
        >
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-gray-100">Pipeline Quality Summary</span>
            <SummaryBadge summary={summary} />
          </div>
          <span className="text-gray-400 text-xs">{expanded ? '▾' : '▸'}</span>
        </button>
        {expanded && (
          <div className="px-4 pb-4 space-y-3">
            <SummaryHeadline summary={summary} />
            {summary.has_ground_truth ? (
              <div className="space-y-2">
                <StageRow name="Stock BM25" stage={summary.stock_bm25} />
                <StageRow
                  name="Your BM25"
                  stage={summary.bm25}
                  badge={<DegradedBadge optimizations={summary.optimizations} />}
                />
                <StageRow name="Hybrid" stage={summary.hybrid} />
                <StageRow name="Reranked" stage={summary.reranked} />
              </div>
            ) : (
              <ConfidenceCard summary={summary} />
            )}
            {summary.generation && <GenerationCard judgment={summary.generation} />}
            <LatencyTable rows={summary.latency} />
            <FootnoteText summary={summary} />
          </div>
        )}
      </div>
    </div>
  )
}

function SummaryBadge({ summary }: { summary: PipelineSummaryEvent }) {
  if (summary.has_ground_truth) {
    return (
      <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full border bg-blue-900/40 text-blue-200 border-blue-700/50">
        ground truth
      </span>
    )
  }
  if (!summary.confidence) return null
  const tone = CONFIDENCE_TONE[summary.confidence.confidence_label]
  return (
    <span
      className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full border ${tone.chip}`}
    >
      proxy · {summary.confidence.confidence_label} confidence
    </span>
  )
}

function SummaryHeadline({ summary }: { summary: PipelineSummaryEvent }) {
  if (summary.has_ground_truth) {
    return (
      <p className="text-xs text-gray-300 leading-relaxed">
        Offline IR metrics for{' '}
        <span className="text-gray-100 font-medium">"{summary.query}"</span> against ESCI
        ground-truth judgments. Higher is better; compare each stage to the BM25 baseline to see
        where the pipeline earns its latency.
      </p>
    )
  }
  return (
    <p className="text-xs text-gray-300 leading-relaxed">
      No ESCI ground truth for this query — falling back to self-referential reranker confidence.
      <span className="text-gray-500"> (These signals are not offline-truth NDCG.)</span>
    </p>
  )
}

function ConfidenceCard({ summary }: { summary: PipelineSummaryEvent }) {
  const c = summary.confidence
  if (!c) return null
  const tone = CONFIDENCE_TONE[c.confidence_label]
  return (
    <div className="rounded-md border border-gray-700/50 bg-gray-800/40 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full ${tone.dot}`} />
        <span className={`text-sm font-medium ${tone.text}`}>
          {c.confidence_label[0].toUpperCase() + c.confidence_label.slice(1)} confidence
        </span>
      </div>
      <div className="grid grid-cols-4 gap-3">
        <MetricCell
          label="Top-1 score"
          value={fmt(c.top1_score, 3)}
          hint="Highest reranker score across the result set"
        />
        <MetricCell
          label="Top-1 gap"
          value={fmt(c.score_gap, 3)}
          hint="Difference between top-1 and top-2 — bigger is more decisive"
        />
        <MetricCell
          label="Variance"
          value={fmt(c.score_variance, 4)}
          hint="Score spread across top-k — wider is more discriminative"
        />
        <MetricCell
          label="Rank churn"
          value={`${c.rank_changes_count}`}
          hint="How many top-10 positions changed pre/post reranker"
        />
      </div>
    </div>
  )
}

function GenerationCard({ judgment }: { judgment: GenerationJudgment }) {
  const tone = VERDICT_TONE[judgment.verdict]
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] uppercase tracking-wide text-gray-400">
          Generation (LLM-as-judge)
        </span>
        <span
          className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full border ${tone.chip}`}
        >
          {tone.label}
        </span>
      </div>
      <div className="rounded-md border border-gray-700/50 bg-gray-800/40 p-3 space-y-2">
        <p className="text-xs text-gray-200 leading-snug italic">
          “{judgment.pairwise_justification}”
        </p>
        <div className="grid grid-cols-4 gap-3">
          <MetricCell
            label="Faithful"
            value={fmt(judgment.faithfulness, 2)}
            hint="1.0 = every claim grounded in retrieved docs (no hallucinations)"
          />
          <MetricCell
            label="Relevance"
            value={fmt(judgment.answer_relevance, 2)}
            hint="How well the response addresses the user's query intent"
          />
          <MetricCell
            label="Citations"
            value={fmt(judgment.citation_accuracy, 2)}
            hint="If the response cites products, the citations match what it says about them"
          />
          <MetricCell
            label="Coverage"
            value={fmt(judgment.context_utilization, 2)}
            hint="Fraction of retrieved products meaningfully referenced"
          />
        </div>
        {judgment.hallucinations.length > 0 && (
          <div className="border-t border-gray-700/50 pt-2 space-y-1">
            <span className="text-[11px] uppercase tracking-wide text-rose-300">
              Hallucinations flagged ({judgment.hallucinations.length})
            </span>
            <ul className="text-xs text-rose-200/90 list-disc list-inside space-y-0.5">
              {judgment.hallucinations.map((h, i) => (
                <li key={i}>{h}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

function DegradedBadge({ optimizations }: { optimizations: Record<string, boolean> }) {
  const off = BM25_TUNING_KEYS.filter((k) => optimizations[k] === false)
  if (off.length === 0) return null
  return (
    <span
      className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded border bg-amber-900/40 text-amber-200 border-amber-700/50"
      title={`These BM25 optimizations are off: ${off.join(', ')}. "Your BM25" reflects the degraded build.`}
    >
      ⚠ {off.length} off
    </span>
  )
}

function FootnoteText({ summary }: { summary: PipelineSummaryEvent }) {
  if (summary.has_ground_truth) {
    return (
      <p className="text-[11px] text-gray-500 leading-snug">
        ESCI relevance scale: Exact=4.0, Substitute=1.0, Complement=0.1, Irrelevant=0.0.
        "Lift / 100ms" is the marginal NDCG gain divided by the marginal latency in 100ms units.
      </p>
    )
  }
  return (
    <p className="text-[11px] text-gray-500 leading-snug">
      Confidence is a heuristic over reranker scores when no ground truth exists. Ingest ESCI
      judgments (`PYTHONPATH=. python ingest_esci_judgments.py`) to enable NDCG/MRR/Recall@20.
    </p>
  )
}
