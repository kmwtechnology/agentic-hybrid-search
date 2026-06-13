/**
 * Lucille custom enrichment stage: Normalize color and brand attributes.
 *
 * Adds derived fields to each document during ingest:
 * - product_color_primary: normalized primary color for filtering
 * - product_color_secondary: normalized secondary color (if present)
 * - product_brand_normalized: normalized brand for filtering
 */

import java.util.regex.Pattern

class ColorNormalizer {
    private static final Map<String, List<String>> BASE_COLORS = [
        'black': ['black', 'jet', 'charcoal', 'ebony', 'onyx'],
        'white': ['white', 'ivory', 'cream', 'off-white', 'ecru', 'beige', 'bone'],
        'blue': ['blue', 'navy', 'cyan', 'turquoise', 'teal', 'aqua', 'indigo', 'cobalt', 'denim'],
        'red': ['red', 'crimson', 'scarlet', 'maroon', 'burgundy', 'wine', 'rust', 'brick'],
        'green': ['green', 'lime', 'emerald', 'sage', 'olive', 'mint', 'forest', 'moss', 'hunter'],
        'yellow': ['yellow', 'gold', 'amber', 'tan', 'khaki', 'mustard', 'champagne'],
        'pink': ['pink', 'rose', 'mauve', 'salmon', 'blush', 'coral', 'fuchsia', 'magenta'],
        'purple': ['purple', 'violet', 'lavender', 'plum', 'lilac', 'eggplant'],
        'brown': ['brown', 'chocolate', 'bronze', 'copper', 'cognac', 'taupe', 'mocha', 'espresso', 'coffee', 'caramel'],
        'gray': ['gray', 'grey', 'silver', 'ash', 'slate', 'pewter', 'graphite', 'nickel', 'chrome', 'titanium'],
        'orange': ['orange', 'coral', 'peach', 'tangerine', 'apricot'],
        'clear': ['clear', 'transparent', 'translucent', 'crystal'],
        'multicolor': ['multicolor', 'multicolored', 'multi-color', 'multi-colored', 'multi', 'rainbow', 'colorful'],
        'natural': ['natural', 'wood', 'natural wood', 'unfinished', 'raw'],
        'mixed': ['assorted', 'mixed', 'various', 'pattern'],
    ]

    private static final Set<String> GENERIC_BRANDS = [
        'generic', 'unknown', 'unbranded', 'brand not specified',
        'as shown', 'various', 'multiple', 'not specified',
    ]

    private Map<String, String> colorLookup

    ColorNormalizer() {
        this.colorLookup = [:]
        BASE_COLORS.each { canonical, variants ->
            variants.each { variant ->
                colorLookup[variant.toLowerCase()] = canonical
            }
        }
    }

    List<String> normalizeColor(String colorStr) {
        if (!colorStr?.trim()) {
            return [null, null]
        }

        String normalized = colorStr.toLowerCase()

        // Strip leading single letter + space
        normalized = normalized.replaceAll(/^[a-z]\s+/, '')

        // Strip trailing noise (numbers, symbols)
        normalized = normalized.replaceAll(/[\s#]*\d+\s*$/, '')
        normalized = normalized.replaceAll(/[\s]*[.!?]\s*$/, '')

        // Normalize special characters (split on &, /, +, ,)
        normalized = normalized.replaceAll(/\s*[&/+,]\s*/, '|')

        // Strip descriptive prefixes
        normalized = normalized.replaceAll(
            /^(light|dark|pale|deep|bright|soft|matte|glossy|metallic|neon|electric|hot|cool|warm|baby|vintage|antique|distressed|faded|heather|sparkle)\s+/,
            ''
        )

        // Remove parenthetical content
        normalized = normalized.replaceAll(/\s*\([^)]*\)/, '')

        // Split by separator and find base colors
        List<String> parts = normalized.split(/\|/).collect { it.trim() }
        List<String> foundColors = []

        parts.each { part ->
            part.split(/\s+/).each { word ->
                String cleanWord = word.replaceAll(/[s,.\-]+$/, '')
                String canonical = colorLookup[cleanWord]
                if (canonical) {
                    foundColors.add(canonical)
                    return // break inner loop
                }
            }
        }

        // Deduplicate while preserving order
        foundColors = foundColors.unique()

        String primary = foundColors.size() > 0 ? foundColors[0] : null
        String secondary = foundColors.size() > 1 ? foundColors[1] : null

        return [primary, secondary]
    }

    String normalizeBrand(String brandStr) {
        if (!brandStr?.trim()) {
            return 'generic'
        }

        String normalized = brandStr.toLowerCase().trim()

        if (normalized in GENERIC_BRANDS) {
            return 'generic'
        }

        return normalized
    }
}

// Initialize normalizer (created once per Lucille execution)
static ColorNormalizer normalizer = new ColorNormalizer()

// Process each document
doc.apply {
    String productColor = doc.product_color?.toString()
    String productBrand = doc.product_brand?.toString()

    // Normalize color
    if (productColor) {
        List<String> colorResult = normalizer.normalizeColor(productColor)
        if (colorResult[0]) {
            doc.product_color_primary = colorResult[0]
        }
        if (colorResult[1]) {
            doc.product_color_secondary = colorResult[1]
        }
    }

    // Normalize brand
    if (productBrand) {
        doc.product_brand_normalized = normalizer.normalizeBrand(productBrand)
    }
}
