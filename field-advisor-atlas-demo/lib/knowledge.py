"""Synthetic agronomy knowledge base for the Field Advisor demo.

Every article is invented for the demo. Content is written to read like real
grower-advisory guidance so semantic retrieval feels genuine, but no article,
product, or company here corresponds to any real organization or brand.
"""

# Each entry: title, crop, region, season, product_line, severity, summary,
# body, tags. The body is what makes vector search feel useful — paraphrased
# grower questions retrieve the article that shares the underlying meaning.
ARTICLES = [
    {
        "title": "Yellowing lower leaves in corn during rapid growth",
        "crop": "Corn", "region": "Midwest", "season": "Vegetative",
        "product_line": "Digital Agronomy", "severity": "Medium",
        "summary": "Lower-leaf yellowing in fast-growing corn usually points to "
                   "nitrogen moving up the plant, not disease.",
        "body": "When corn yellows from the bottom up during rapid vegetative "
                "growth, the most common cause is nitrogen translocation: the "
                "plant pulls mobile nitrogen from older leaves to feed new "
                "growth. Confirm with a tissue test before treating. Split "
                "sidedress applications and consider a stabilized nitrogen "
                "source on sandy soils prone to leaching after heavy rain.",
        "tags": ["nitrogen", "chlorosis", "leaf yellowing", "tissue test"],
    },
    {
        "title": "Managing early-season sudden death and root rot in soybeans",
        "crop": "Soybean", "region": "Midwest", "season": "Planting",
        "product_line": "Seed Treatment", "severity": "High",
        "summary": "Cool, wet planting conditions raise the risk of root-rot "
                   "complexes; a seed treatment plus drainage helps.",
        "body": "Soybeans planted into cool, saturated soils are vulnerable to "
                "root-rot and sudden-death complexes that show up later as "
                "interveinal yellowing and plant death in patches. Use a "
                "fungicide seed treatment rated for these pathogens, avoid "
                "planting into waterlogged fields, and improve drainage in "
                "chronically wet field zones to reduce recurrence.",
        "tags": ["root rot", "sudden death", "seed treatment", "wet soils"],
    },
    {
        "title": "Wheat leaf rust identification and spray timing",
        "crop": "Wheat", "region": "Great Plains", "season": "Flowering",
        "product_line": "Fungicide", "severity": "High",
        "summary": "Orange pustules on the upper leaf surface signal leaf rust; "
                   "protect the flag leaf around heading.",
        "body": "Leaf rust appears as small orange-brown pustules scattered on "
                "the upper leaf surface. Yield loss is driven by damage to the "
                "flag leaf, so the highest-value fungicide window is from flag-"
                "leaf emergence through heading. Scout susceptible varieties "
                "first and prioritize spraying when rust is found before "
                "flowering under warm, humid conditions.",
        "tags": ["leaf rust", "flag leaf", "fungicide timing", "pustules"],
    },
    {
        "title": "Herbicide-resistant waterhemp management in soybeans",
        "crop": "Soybean", "region": "Midwest", "season": "Vegetative",
        "product_line": "Herbicide", "severity": "Critical",
        "summary": "Waterhemp escapes often mean resistance; layer residuals and "
                   "diversify sites of action.",
        "body": "Waterhemp that survives a post-emergence pass is frequently "
                "resistant to one or more herbicide groups. Start clean, apply "
                "an effective pre-emergence residual, and overlap residuals "
                "before the weed reaches four inches. Rotate and tank-mix "
                "multiple effective sites of action, and control late escapes "
                "before they set seed to protect future seasons.",
        "tags": ["waterhemp", "resistance", "residual herbicide", "sites of action"],
    },
    {
        "title": "Scouting for corn rootworm feeding pressure",
        "crop": "Corn", "region": "Great Plains", "season": "Vegetative",
        "product_line": "Insecticide", "severity": "High",
        "summary": "Lodging and 'gooseneck' plants signal rootworm larval "
                   "feeding; rotate traits and crops.",
        "body": "Corn rootworm larvae feed on roots, causing lodging and the "
                "characteristic goosenecked stalks after storms. Dig and rate "
                "root injury, and use beetle traps to forecast next-year "
                "pressure. Rotate rootworm-active traits, rotate crops where "
                "feasible, and consider a soil insecticide in continuous-corn "
                "fields with a history of heavy pressure.",
        "tags": ["rootworm", "lodging", "gooseneck", "trait rotation"],
    },
    {
        "title": "Cotton bollworm thresholds and beneficial insects",
        "crop": "Cotton", "region": "Southeast", "season": "Flowering",
        "product_line": "Insecticide", "severity": "Medium",
        "summary": "Treat bollworm on egg-lay and small-larva counts; preserve "
                   "beneficials to avoid secondary flares.",
        "body": "Bollworm decisions in cotton hinge on scouting eggs and small "
                "larvae against the local threshold rather than moth counts "
                "alone. Broad-spectrum sprays can flare aphids and mites by "
                "removing beneficial insects, so choose selective chemistry "
                "when possible and rotate modes of action to slow resistance.",
        "tags": ["bollworm", "threshold", "beneficials", "resistance"],
    },
    {
        "title": "Rice sheath blight in high-nitrogen, dense canopies",
        "crop": "Rice", "region": "Southeast", "season": "Vegetative",
        "product_line": "Fungicide", "severity": "High",
        "summary": "Dense, over-fertilized rice canopies favor sheath blight; "
                   "manage nitrogen and time fungicide at panicle initiation.",
        "body": "Sheath blight thrives in humid, dense rice canopies pushed by "
                "excess nitrogen. Lesions start near the waterline and climb "
                "the sheath. Avoid over-fertilizing, keep balanced potassium, "
                "and target fungicide from panicle initiation to early heading "
                "on susceptible varieties with a history of the disease.",
        "tags": ["sheath blight", "nitrogen", "canopy", "panicle initiation"],
    },
    {
        "title": "Canola flea beetle protection at emergence",
        "crop": "Canola", "region": "Mountain West", "season": "Planting",
        "product_line": "Seed Treatment", "severity": "Medium",
        "summary": "Cotyledon-stage flea beetle feeding can thin stands fast; "
                   "seed treatment plus scouting protects the window.",
        "body": "Flea beetles attack canola cotyledons and can rapidly reduce "
                "stands under warm, dry spring conditions. An insecticidal seed "
                "treatment protects the critical emergence-to-four-leaf window. "
                "Scout warm afternoons and be ready with a foliar rescue spray "
                "if defoliation approaches the action threshold before the crop "
                "outgrows the risk.",
        "tags": ["flea beetle", "cotyledon", "seed treatment", "stand loss"],
    },
    {
        "title": "Biological inoculants for improving soybean nodulation",
        "crop": "Soybean", "region": "Midwest", "season": "Pre-plant",
        "product_line": "Biologicals", "severity": "Low",
        "summary": "Fields new to soybeans or with high pH may nodulate poorly; "
                   "a rhizobium inoculant restores nitrogen fixation.",
        "body": "Poor nodulation shows up as pale, stunted soybeans and few "
                "pink nodules on the roots. Fields without a recent soybean "
                "history, or with high pH and low organic matter, benefit most "
                "from a rhizobium inoculant applied at planting. Keep the "
                "product cool, avoid mixing with harsh seed-applied chemistry, "
                "and dig plants at V3 to confirm active nodules formed.",
        "tags": ["inoculant", "nodulation", "nitrogen fixation", "biologicals"],
    },
    {
        "title": "Using satellite imagery to prioritize in-season scouting",
        "crop": "Corn", "region": "Midwest", "season": "Vegetative",
        "product_line": "Digital Agronomy", "severity": "Low",
        "summary": "Vegetation-index maps flag stressed zones so field teams "
                   "scout the right acres first.",
        "body": "In-season imagery and vegetation indices highlight zones where "
                "the crop is under stress before it is obvious from the road. "
                "Use the maps to route scouts to the weakest areas, then ground-"
                "truth the cause — compaction, drainage, nutrient deficiency, "
                "or pest pressure — before prescribing a treatment. This turns "
                "limited scouting hours into targeted, higher-value visits.",
        "tags": ["imagery", "ndvi", "scouting", "variable rate"],
    },
    {
        "title": "Pre-harvest desiccation timing to reduce green stem",
        "crop": "Soybean", "region": "Great Plains", "season": "Harvest",
        "product_line": "Herbicide", "severity": "Medium",
        "summary": "A properly timed harvest aid evens up dry-down and eases "
                   "combining in weedy or uneven fields.",
        "body": "Green stem and late-season weeds slow harvest and raise "
                "moisture variability. A harvest-aid application timed once the "
                "crop reaches physiological maturity can even out dry-down and "
                "improve combine efficiency. Follow the required pre-harvest "
                "interval on the label and confirm the crop has reached the "
                "correct staging before applying to protect grain quality.",
        "tags": ["desiccation", "harvest aid", "green stem", "dry down"],
    },
    {
        "title": "Wheat stripe rust in cool, wet Pacific Northwest springs",
        "crop": "Wheat", "region": "Pacific Northwest", "season": "Vegetative",
        "product_line": "Fungicide", "severity": "Critical",
        "summary": "Cool, moist conditions drive explosive stripe rust; scout "
                   "early and protect susceptible varieties.",
        "body": "Stripe rust forms yellow-orange pustules in stripes between "
                "leaf veins and explodes under cool, wet spring weather common "
                "in the Pacific Northwest. On susceptible varieties an early "
                "fungicide can pay off well before the flag leaf if disease is "
                "already active. Track regional rust forecasts and prioritize "
                "the most susceptible fields for the first pass.",
        "tags": ["stripe rust", "cool wet", "susceptible variety", "fungicide"],
    },
]
