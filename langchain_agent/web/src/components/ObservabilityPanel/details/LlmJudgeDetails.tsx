/**
 * Step-level details for the llm_judge node.
 *
 * Mirrors what the Pipeline Quality Summary card already renders, just at
 * the per-step level so collapsing/reopening the LLM Judge step keeps a
 * meaningful summary visible.
 */

import { useObservabilityStore } from '../../../stores/observabilityStore'
import { useOptimizationsStore } from '../../../stores/optimizationsStore'
import type { GenerationJudgment, ObservabilityStep } from '../../../types/events'

function fmt(n: number, digits = 2): string {
  return n.toFixed(digits)
}

const VERDICT_COPY: Record<GenerationJudgment['verdict'], string> = {
  llm_better: 'LLM judged BETTER',
  tied: 'Tied',
  llm_worse: 'LLM judged WORSE',
}

export function LlmJudgeDetails({ step }: { step?: ObservabilityStep }) {
  const summary = useObservabilityStore((s) => s.pipelineSummary)
  const optimizations = useOptimizationsStore((s) => s.optimizations)
  const judgment = summary?.generation
  const original = summary?.original_generation
  const retried = !!summary?.hallucination_retry_used

  if (!judgment) {
    // The judge result hasn't surfaced. Be specific about why so the user
    // doesn't see a misleading "skipped" message in cases like:
    //   1. step is still running → judge is in flight
    //   2. step finished but PipelineSummaryEvent hasn't been emitted yet
    //   3. toggle was off when the query ran
    //   4. fresh page load wiped the per-session pipelineSummary
    if (step?.status === 'running') {
      return (
        <div className="text-sm text-gray-400 italic space-y-1">
          <p>Judging in progress…</p>
          <p className="text-xs not-italic text-gray-500">
            Initial scoring takes ~1–2s. If hallucinations are flagged, an
            auto-correction retry kicks in (re-prompts the agent + re-judges)
            which can push the total to 20–30s.
          </p>
        </div>
      )
    }
    const llmOn = optimizations.llm
    const judgeOn = optimizations.llm_judge
    if (!llmOn) {
      return (
        <div className="text-sm text-gray-500">
          Judge needs <code>llm</code> on. Currently <code>llm</code> is OFF — there's
          no synthesized response to compare against.
        </div>
      )
    }
    if (!judgeOn) {
      return (
        <div className="text-sm text-gray-500">
          Judge toggle is currently OFF. Toggle <code>llm_judge</code> on in the
          Search Optimizations card to enable the Generation row on the next query.
        </div>
      )
    }
    return (
      <div className="text-sm text-gray-500 space-y-2">
        <p>
          No judge result for this turn. The toggles are currently both{' '}
          <code>llm</code> and <code>llm_judge</code> on, but the query you're
          looking at probably ran with one of them off.
        </p>
        <p className="text-xs text-gray-600">
          Send a new query — the judge runs at the end of every retrieval and
          its result will populate this step (and the Pipeline Quality Summary
          card below) automatically.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="font-medium text-gray-100">{VERDICT_COPY[judgment.verdict]}</span>
        {retried && (
          <span
            className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full border bg-amber-900/40 text-amber-200 border-amber-700/50"
            title="Auto-correction was applied because the original response had hallucinations."
          >
            🔁 Auto-corrected
          </span>
        )}
      </div>

      <p className="text-xs text-gray-300 leading-snug italic break-words">
        “{judgment.pairwise_justification}”
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-3 gap-y-2 text-center">
        <Score label="Faithful" value={judgment.faithfulness} prev={original?.faithfulness} />
        <Score
          label="Relevance"
          value={judgment.answer_relevance}
          prev={original?.answer_relevance}
        />
        <Score
          label="Citations"
          value={judgment.citation_accuracy}
          prev={original?.citation_accuracy}
        />
        <Score
          label="Coverage"
          value={judgment.context_utilization}
          prev={original?.context_utilization}
        />
      </div>

      {original && retried && (
        <p className="text-[11px] text-gray-500 leading-snug">
          Pre-retry: faithfulness {fmt(original.faithfulness)}, {original.hallucinations.length}{' '}
          hallucination{original.hallucinations.length === 1 ? '' : 's'} flagged. Post-retry:
          faithfulness {fmt(judgment.faithfulness)}, {judgment.hallucinations.length} flagged.
        </p>
      )}

      {judgment.hallucinations.length > 0 && (
        <div className="border-t border-gray-700/40 pt-2 space-y-1">
          <span className="text-[11px] uppercase tracking-wide text-rose-300">
            Hallucinations flagged ({judgment.hallucinations.length})
          </span>
          <ul className="text-xs text-rose-200/90 list-disc list-outside ml-4 space-y-0.5 break-words">
            {judgment.hallucinations.map((h, i) => (
              <li key={i}>{h}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Score({ label, value, prev }: { label: string; value: number; prev?: number }) {
  const delta = prev !== undefined ? value - prev : null
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-gray-400">{label}</span>
      <span className="font-mono text-sm text-gray-100 tabular-nums">{fmt(value)}</span>
      {delta !== null && Math.abs(delta) >= 0.005 && (
        <span
          className={`text-[10px] tabular-nums ${
            delta > 0 ? 'text-emerald-300' : 'text-rose-300'
          }`}
          title={`Was ${fmt(prev!)} before retry`}
        >
          {delta > 0 ? '+' : ''}
          {fmt(delta)}
        </span>
      )}
    </div>
  )
}
