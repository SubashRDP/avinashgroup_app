// Step-by-step guide, in English and Nepali, on every document of the purchase
// flow: Material Request -> Request for Quotation -> Supplier Quotation ->
// comparison -> Purchase Order -> approval. Each form gets a "Guide" button that
// opens the guide for that document, with the whole flow shown on top and the
// current stage marked, so a new user always knows what to do here and next.
//
// Loaded as doctype_js on the four buying forms (hooks.py) and by the Supplier
// Quotation Comparison report (frappe.require). The language choice is remembered
// per browser.
(() => {
	window.avinashgroup_app = window.avinashgroup_app || {};
	if (window.avinashgroup_app.buying_guide) return; // already loaded by another form

	const LANG_KEY = "avinashgroup_buying_guide_lang";
	const BUTTON_LABEL = "📘 Guide / मार्गदर्शन";

	const STAGES = [
		{ key: "mr", icon: "📝", en: "Material Request", ne: "सामग्री माग" },
		{ key: "rfq", icon: "📨", en: "Request for Quotation", ne: "दरभाउ अनुरोध" },
		{ key: "sq", icon: "🧾", en: "Supplier Quotation", ne: "आपूर्तिकर्ताको दरभाउ" },
		{ key: "compare", icon: "⚖️", en: "Compare", ne: "तुलना" },
		{ key: "po", icon: "📦", en: "Purchase Order", ne: "खरिद आदेश" },
		{ key: "approve", icon: "✅", en: "Approval", ne: "स्वीकृति" },
	];

	const LABELS = {
		en: {
			flow: "Purchase flow",
			here: "You are here",
			purpose: "What this document is for",
			steps: "Do this, step by step",
			tips: "Good to know",
			avoid: "Avoid these mistakes",
			next: "Next",
		},
		ne: {
			flow: "खरिद प्रक्रिया",
			here: "तपाईं यहाँ हुनुहुन्छ",
			purpose: "यो कागजात केका लागि हो",
			steps: "यसरी गर्नुहोस् — चरणबद्ध",
			tips: "जान्नु राम्रो",
			avoid: "यी गल्ती नगर्नुहोस्",
			next: "अर्को",
		},
	};

	// **text** renders bold - used for the buttons and fields to look for.
	const GUIDES = {
		mr: {
			stages: ["mr"],
			en: {
				title: "Material Request — ask for what you need",
				purpose:
					"Every purchase starts here. Tell the purchase team which items you need, how many, and by when. Nothing is bought without a submitted Material Request.",
				steps: [
					["Fill in the basics", "Choose the **Company**, keep **Purpose = Purchase**, and set the **Required Miti** (the date you need the goods by). Pick your **Branch** — the right buying warehouse is filled in for you."],
					["Add each item", "Enter the **Item**, **Qty** and unit. Write size, brand or anything the supplier must know in **Narration**. For vehicle parts, choose the **Vehicle**."],
					["Check, then Save", "Read the quantities once more — the purchase team asks for prices and orders exactly these."],
					["Submit", "**Submit** sends the request forward. After that it can't be edited; if something is wrong, **Cancel** and **Amend** it."],
					["Ask suppliers for prices", "Use **Create ▸ Request for Quotation** to send the items to 2–3 suppliers. If a supplier has already given a price, use **Create ▸ Supplier Quotation** instead."],
				],
				tips: [
					"The warehouse fills itself from the item and your branch — you don't need to type it.",
					"Click **Supplier Quotation Comparison** on this form any time to see every price received for this request.",
				],
				avoid: [
					"Don't make a Purchase Order straight from here — this company buys only through quotations, so that button is hidden on purpose.",
					"Wrong quantity after submitting? **Cancel** and **Amend** — don't make a second request for the same items.",
				],
				next: "Request for Quotation — **Create ▸ Request for Quotation**",
			},
			ne: {
				title: "सामग्री माग (Material Request) — चाहिने सामान माग्नुहोस्",
				purpose:
					"हरेक खरिद यहीँबाट सुरु हुन्छ। कुन सामान, कति परिमाणमा र कहिलेसम्म चाहिन्छ भनेर खरिद शाखालाई जानकारी दिनुहोस्। Submit भएको सामग्री माग बिना कुनै खरिद हुँदैन।",
				steps: [
					["आधारभूत विवरण भर्नुहोस्", "**Company** छान्नुहोस्, **Purpose = Purchase** नै राख्नुहोस् र **Required Miti** (सामान चाहिने मिति) राख्नुहोस्। आफ्नो **Branch** छान्नुहोस् — सही गोदाम आफैँ भरिन्छ।"],
					["हरेक सामान थप्नुहोस्", "**Item**, **Qty** र एकाइ राख्नुहोस्। साइज, ब्रान्ड वा आपूर्तिकर्ताले जान्नुपर्ने कुरा **Narration** मा लेख्नुहोस्। सवारी साधनको पार्टपुर्जा भए **Vehicle** छान्नुहोस्।"],
					["जाँचेर Save गर्नुहोस्", "परिमाण फेरि एकपटक जाँच्नुहोस् — खरिद शाखाले ठ्याक्कै यही परिमाणको दरभाउ माग्छ र आदेश दिन्छ।"],
					["Submit गर्नुहोस्", "**Submit** गरेपछि माग अगाडि बढ्छ र सम्पादन गर्न मिल्दैन। गल्ती भए **Cancel** गरी **Amend** गर्नुहोस्।"],
					["आपूर्तिकर्तासँग दर माग्नुहोस्", "**Create ▸ Request for Quotation** बाट २–३ आपूर्तिकर्तालाई सामानको सूची पठाउनुहोस्। आपूर्तिकर्ताले पहिले नै दर दिइसकेको भए **Create ▸ Supplier Quotation** गर्नुहोस्।"],
				],
				tips: [
					"गोदाम सामान र शाखाअनुसार आफैँ भरिन्छ — टाइप गर्नु पर्दैन।",
					"यो माग विरुद्ध आएका सबै दर हेर्न यसै फारमको **Supplier Quotation Comparison** बटन थिच्नुहोस्।",
				],
				avoid: [
					"यहाँबाट सिधै खरिद आदेश नबनाउनुहोस् — यो कम्पनीमा खरिद दरभाउ मार्फत मात्र हुन्छ, त्यसैले त्यो बटन जानाजानी लुकाइएको छ।",
					"Submit पछि परिमाण गलत भए **Cancel** र **Amend** गर्नुहोस् — उही सामानका लागि दोस्रो माग नबनाउनुहोस्।",
				],
				next: "दरभाउ अनुरोध — **Create ▸ Request for Quotation**",
			},
		},

		rfq: {
			stages: ["rfq"],
			en: {
				title: "Request for Quotation — ask suppliers for prices",
				purpose:
					"One request sent to several suppliers, so the same items can be priced and compared fairly.",
				steps: [
					["Start from the Material Request", "Open the submitted Material Request ▸ **Create ▸ Request for Quotation**. Items, quantities and warehouse come across by themselves."],
					["Add the suppliers", "In the **Suppliers** table add every supplier you want a price from — at least 2–3. If you will email it, check each supplier has an email."],
					["Date and message", "Set the **Required Miti** (when you need the prices) and write a short message: delivery place, terms, anything special."],
					["Save and Submit", "**Submit** locks the request. You can then email it to the suppliers or print it."],
					["Record each supplier's reply", "When a supplier replies, open this RFQ ▸ **Create ▸ Supplier Quotation**, choose that supplier and enter the prices. One Supplier Quotation per supplier."],
				],
				tips: [
					"Keep the quantities the same as the Material Request, so every supplier prices the same thing.",
					"Need one more supplier later? **Amend** the request and add them.",
				],
				avoid: [
					"Don't type the items by hand — always start from the Material Request so every document stays linked.",
					"Never put two suppliers' prices in one quotation.",
				],
				next: "Supplier Quotation — **Create ▸ Supplier Quotation** for each supplier who replied",
			},
			ne: {
				title: "दरभाउ अनुरोध (Request for Quotation) — आपूर्तिकर्तासँग दर माग्नुहोस्",
				purpose:
					"एउटै अनुरोध धेरै आपूर्तिकर्तालाई पठाइन्छ, ताकि एउटै सामानको दर निष्पक्ष रूपमा तुलना गर्न सकियोस्।",
				steps: [
					["सामग्री मागबाट सुरु गर्नुहोस्", "Submit भएको सामग्री माग खोल्नुहोस् ▸ **Create ▸ Request for Quotation**। सामान, परिमाण र गोदाम आफैँ आउँछन्।"],
					["आपूर्तिकर्ता थप्नुहोस्", "**Suppliers** तालिकामा दर लिन चाहेका सबै आपूर्तिकर्ता — कम्तीमा २–३ — थप्नुहोस्। इमेलबाट पठाउने भए हरेकको इमेल छ कि छैन जाँच्नुहोस्।"],
					["मिति र सन्देश", "**Required Miti** (दर चाहिने मिति) राख्नुहोस् र छोटो सन्देश लेख्नुहोस्: डेलिभरी स्थान, सर्तहरू, विशेष कुरा।"],
					["Save र Submit", "**Submit** गरेपछि अनुरोध पक्का हुन्छ। त्यसपछि आपूर्तिकर्तालाई इमेल गर्न वा प्रिन्ट गर्न सकिन्छ।"],
					["हरेक आपूर्तिकर्ताको जवाफ राख्नुहोस्", "आपूर्तिकर्ताले दर पठाएपछि यही RFQ खोल्नुहोस् ▸ **Create ▸ Supplier Quotation**, त्यो आपूर्तिकर्ता छान्नुहोस् र दर राख्नुहोस्। एक आपूर्तिकर्ता = एक Supplier Quotation।"],
				],
				tips: [
					"परिमाण सामग्री माग जस्तै राख्नुहोस्, ताकि सबै आपूर्तिकर्ताले एउटै कुराको दर देऊन्।",
					"पछि अर्को आपूर्तिकर्ता चाहिए अनुरोधलाई **Amend** गरेर थप्नुहोस्।",
				],
				avoid: [
					"सामान हातले टाइप नगर्नुहोस् — सधैँ सामग्री मागबाट सुरु गर्नुहोस्, ताकि सबै कागजात जोडिएका रहून्।",
					"दुई आपूर्तिकर्ताको दर कहिल्यै एउटै दरभाउमा नराख्नुहोस्।",
				],
				next: "आपूर्तिकर्ताको दरभाउ — जवाफ दिने हरेक आपूर्तिकर्ताका लागि **Create ▸ Supplier Quotation**",
			},
		},

		sq: {
			stages: ["sq"],
			en: {
				title: "Supplier Quotation — enter one supplier's offer",
				purpose:
					"Record exactly what one supplier offered — prices, taxes, delivery and terms. These are what get compared.",
				steps: [
					["Start from the RFQ", "From the Request for Quotation ▸ **Create ▸ Supplier Quotation**, choose the supplier. Items and quantities come across. (No RFQ? Start from the Material Request the same way.)"],
					["Enter the rates", "Type the supplier's **Rate** for every item. If they offer a different quantity, change the **Qty** — it will show in orange on the comparison."],
					["Taxes on each line", "Set **VAT Apply On / VAT Rate**, **TDS** and **Excise** on each item exactly as on the supplier's paper. The VAT, TDS and Excise totals work themselves out."],
					["Terms", "Fill **Specification**, **Warranty**, **Payment Terms**, **Delivery Period** and **Valid Miti**. They appear under this supplier in the comparison."],
					["Mark it preferred", "Tick **Preferred Quotation** if this offer should be considered. The comparison shows preferred quotations by default."],
					["Save and Submit", "After **Submit** you are taken back to the Material Request to carry on."],
				],
				tips: [
					"Brand or model differs between suppliers? Say so in the item's **Narration**.",
					"Attach the supplier's quotation paper or PDF to this document.",
				],
				avoid: [
					"Forgetting **Preferred Quotation** — the offer then won't show in the comparison unless that filter is unticked.",
					"Adding VAT into the rate yourself — enter the rate as quoted and put the VAT on the line.",
				],
				next: "Compare every offer in the **Supplier Quotation Comparison**",
			},
			ne: {
				title: "आपूर्तिकर्ताको दरभाउ (Supplier Quotation) — एक आपूर्तिकर्ताको प्रस्ताव राख्नुहोस्",
				purpose:
					"एक आपूर्तिकर्ताले दिएको प्रस्ताव — दर, कर, डेलिभरी र सर्तहरू — ठ्याक्कै राख्नुहोस्। तुलना यिनैको हुन्छ।",
				steps: [
					["RFQ बाट सुरु गर्नुहोस्", "दरभाउ अनुरोधबाट ▸ **Create ▸ Supplier Quotation** गरी आपूर्तिकर्ता छान्नुहोस्। सामान र परिमाण आफैँ आउँछन्। (RFQ छैन भने सामग्री मागबाट त्यसै गरी सुरु गर्नुहोस्।)"],
					["दर राख्नुहोस्", "हरेक सामानको आपूर्तिकर्ताले दिएको **Rate** राख्नुहोस्। फरक परिमाण दिएको भए **Qty** परिवर्तन गर्नुहोस् — तुलनामा सुन्तला रङमा देखिन्छ।"],
					["हरेक लाइनको कर", "आपूर्तिकर्ताको कागजमा जस्तै हरेक सामानमा **VAT Apply On / VAT Rate**, **TDS** र **Excise** राख्नुहोस्। कुल VAT, TDS र Excise आफैँ हिसाब हुन्छ।"],
					["सर्तहरू", "**Specification**, **Warranty**, **Payment Terms**, **Delivery Period** र **Valid Miti** भर्नुहोस्। यी तुलनामा यस आपूर्तिकर्तामुनि देखिन्छन्।"],
					["Preferred Quotation", "यो प्रस्ताव विचार गर्नुपर्ने भए **Preferred Quotation** मा टिक लगाउनुहोस्। तुलनाले पूर्वनिर्धारित रूपमा यस्ता दरभाउ मात्र देखाउँछ।"],
					["Save र Submit", "**Submit** गरेपछि तपाईं सामग्री माग पेजमा फर्किनुहुन्छ र काम त्यहीँबाट अगाडि बढ्छ।"],
				],
				tips: [
					"आपूर्तिकर्ताबीच ब्रान्ड वा मोडल फरक छ भने सामानको **Narration** मा लेख्नुहोस्।",
					"आपूर्तिकर्ताको दरभाउ कागज वा PDF यसै कागजातमा Attach गर्नुहोस्।",
				],
				avoid: [
					"**Preferred Quotation** टिक गर्न नबिर्सनुहोस् — नत्र फिल्टर नहटाएसम्म यो प्रस्ताव तुलनामा देखिँदैन।",
					"VAT आफैँ दरभित्र नजोड्नुहोस् — दर जस्तो दिइएको छ त्यस्तै राख्नुहोस् र VAT लाइनमा राख्नुहोस्।",
				],
				next: "सबै प्रस्ताव **Supplier Quotation Comparison** मा तुलना गर्नुहोस्",
			},
		},

		compare: {
			stages: ["compare"],
			en: {
				title: "Supplier Quotation Comparison — choose the best offer",
				purpose:
					"Every quotation for a Material Request side by side: what each supplier quoted, and what has already been ordered.",
				steps: [
					["Open it", "Click **Supplier Quotation Comparison** on the Material Request or Purchase Order. The company, request and dates are filled in for you."],
					["Read one quotation block", "Each coloured block is one quotation: **Quoted** (Qty, Rate, Amount) and **Ordered** (what Purchase Orders took). **MR Qty** is what was asked for; an orange Qty means the supplier offered a different quantity."],
					["Compare totals and terms", "Look at **Total**, **VAT** and **Invoice Amount**, then the terms rows — delivery, warranty, payment."],
					["See every Purchase Order", "Tick **Extend Purchase Order** to see each order's own Qty, Rate and Amount. **★** marks the order you opened from."],
					["Print or export", "**Menu ▸ Print / PDF / Export** keeps this same layout — handy for meetings and files."],
				],
				tips: [
					"Click a quotation or Purchase Order heading to open it.",
					"Untick **Preferred Quotation** to see every quotation, not only the preferred ones.",
				],
				avoid: [
					"A date range can hide quotations — opening from the request or order clears the dates for you.",
				],
				next: "Open the chosen Supplier Quotation ▸ **Create ▸ Purchase Order**",
			},
			ne: {
				title: "दरभाउ तुलना (Supplier Quotation Comparison) — उत्तम प्रस्ताव छान्नुहोस्",
				purpose:
					"एउटा सामग्री मागका सबै दरभाउ एकै ठाउँमा: हरेक आपूर्तिकर्ताले के दर दियो र कति आदेश भइसक्यो।",
				steps: [
					["खोल्नुहोस्", "सामग्री माग वा खरिद आदेशमा **Supplier Quotation Comparison** थिच्नुहोस्। कम्पनी, माग र मिति आफैँ भरिन्छन्।"],
					["एउटा दरभाउ ब्लक पढ्नुहोस्", "हरेक रङीन ब्लक एउटा दरभाउ हो: **Quoted** (Qty, Rate, Amount) र **Ordered** (खरिद आदेशले लिएको)। **MR Qty** माग गरिएको परिमाण हो; सुन्तला रङको Qty भनेको आपूर्तिकर्ताले फरक परिमाण दिएको।"],
					["कुल रकम र सर्त तुलना गर्नुहोस्", "**Total**, **VAT** र **Invoice Amount** हेर्नुहोस्, त्यसपछि सर्तका पङ्क्ति — डेलिभरी, वारेन्टी, भुक्तानी।"],
					["हरेक खरिद आदेश हेर्नुहोस्", "**Extend Purchase Order** मा टिक गर्दा हरेक आदेशको आफ्नै Qty, Rate र Amount देखिन्छ। **★** ले तपाईंले खोलेको आदेश जनाउँछ।"],
					["प्रिन्ट वा Export", "**Menu ▸ Print / PDF / Export** ले यही ढाँचामा फाइल बनाउँछ — बैठक र फाइलका लागि उपयोगी।"],
				],
				tips: [
					"कुनै दरभाउ वा खरिद आदेशको शीर्षकमा क्लिक गर्दा त्यो खुल्छ।",
					"**Preferred Quotation** को टिक हटाए सबै दरभाउ देखिन्छन्।",
				],
				avoid: [
					"मिति फिल्टरले दरभाउ लुकाउन सक्छ — माग वा आदेशबाट खोल्दा मिति आफैँ हट्छ।",
				],
				next: "छानिएको Supplier Quotation खोल्नुहोस् ▸ **Create ▸ Purchase Order**",
			},
		},

		po: {
			stages: ["po", "approve"],
			en: {
				title: "Purchase Order — order from the chosen supplier",
				purpose:
					"The official order to the supplier. It becomes final only after it is approved.",
				steps: [
					["Create it from the chosen quotation", "Open the chosen Supplier Quotation ▸ **Create ▸ Purchase Order**. Supplier, items, rates and taxes come across — don't type them again."],
					["Fill in the order details", "**Department** (required), **Required By**, **Ship To**, **Note for Supplier** and **Remarks**. Remove any item you are not buying from this supplier."],
					["Check the money", "Compare **Value before VAT**, **VAT**, **TDS** and **Excise** with the quotation. Click **Supplier Quotation Comparison** to check against the other offers once more."],
					["Save", "The approval chain for your company and department is set up by itself — see the **Approval Hierarchy** table."],
					["Submit for Approval", "Use **Actions ▸ Submit for Approval**. The status becomes **Pending Approval** and the first approver gets an email."],
					["Approval", "Each approver opens the order and uses **Actions ▸ Approve**, or **Reject** with a reason. After the last approval the order is **Approved** and final. A rejected order is cancelled — **Amend** it to correct and send again."],
				],
				tips: [
					"The **Approval History** table shows who approved and when.",
					"Ordered quantities appear on the comparison as **Ordered 1, Ordered 2…**",
				],
				avoid: [
					"Don't make a Purchase Order from a blank form — start from the Supplier Quotation so it stays linked to the comparison.",
					"Don't change an order while it is **Pending Approval** unless you are asked to — approvers would see the changed version.",
				],
				next: "Done — once **Approved**, send the order to the supplier. When the goods arrive, make a **Purchase Receipt**.",
			},
			ne: {
				title: "खरिद आदेश (Purchase Order) — छानिएको आपूर्तिकर्तालाई आदेश दिनुहोस्",
				purpose:
					"आपूर्तिकर्तालाई दिइने आधिकारिक आदेश। स्वीकृत भएपछि मात्र यो पक्का हुन्छ।",
				steps: [
					["छानिएको दरभाउबाट बनाउनुहोस्", "छानिएको Supplier Quotation खोल्नुहोस् ▸ **Create ▸ Purchase Order**। आपूर्तिकर्ता, सामान, दर र कर आफैँ आउँछन् — फेरि टाइप नगर्नुहोस्।"],
					["आदेशको विवरण भर्नुहोस्", "**Department** (अनिवार्य), **Required By**, **Ship To**, **Note for Supplier** र **Remarks** भर्नुहोस्। यो आपूर्तिकर्ताबाट नकिन्ने सामान हटाउनुहोस्।"],
					["रकम जाँच्नुहोस्", "**Value before VAT**, **VAT**, **TDS** र **Excise** दरभाउसँग मिलाउनुहोस्। अरू प्रस्तावसँग फेरि हेर्न **Supplier Quotation Comparison** थिच्नुहोस्।"],
					["Save गर्नुहोस्", "कम्पनी र विभागअनुसारको स्वीकृति क्रम आफैँ मिलाइन्छ — **Approval Hierarchy** तालिका हेर्नुहोस्।"],
					["Submit for Approval", "**Actions ▸ Submit for Approval** थिच्नुहोस्। स्थिति **Pending Approval** हुन्छ र पहिलो स्वीकृतकर्तालाई इमेल जान्छ।"],
					["स्वीकृति", "हरेक स्वीकृतकर्ताले आदेश खोलेर **Actions ▸ Approve** गर्छन्, वा कारणसहित **Reject** गर्छन्। अन्तिम स्वीकृतिपछि आदेश **Approved** भई पक्का हुन्छ। Reject भएको आदेश रद्द हुन्छ — सच्याउन **Amend** गरी फेरि पठाउनुहोस्।"],
				],
				tips: [
					"कसले कहिले स्वीकृत गर्‍यो भन्ने **Approval History** तालिकामा देखिन्छ।",
					"आदेश गरिएको परिमाण तुलनामा **Ordered 1, Ordered 2…** का रूपमा देखिन्छ।",
				],
				avoid: [
					"खाली फारमबाट खरिद आदेश नबनाउनुहोस् — Supplier Quotation बाट सुरु गर्नुहोस्, ताकि तुलनासँग जोडियोस्।",
					"**Pending Approval** भएको आदेश नभनिकन परिवर्तन नगर्नुहोस् — स्वीकृतकर्ताले परिवर्तित आदेश देख्छन्।",
				],
				next: "पूरा भयो — **Approved** भएपछि आपूर्तिकर्तालाई आदेश पठाउनुहोस्। सामान आएपछि **Purchase Receipt** बनाउनुहोस्।",
			},
		},
	};

	const NEPALI_DIGITS = "०१२३४५६७८९";
	const digits = (n, lang) =>
		lang === "ne" ? String(n).replace(/\d/g, (d) => NEPALI_DIGITS[d]) : String(n);

	const rich = (text) =>
		frappe.utils.escape_html(text).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");

	const get_lang = () => {
		try {
			return localStorage.getItem(LANG_KEY) === "ne" ? "ne" : "en";
		} catch (e) {
			return "en";
		}
	};
	const set_lang = (lang) => {
		try {
			localStorage.setItem(LANG_KEY, lang);
		} catch (e) {
			// private window / blocked storage - the guide still works, just forgets
		}
	};

	const STYLE = `<style>
		.bg-guide { font-size: 14px; color: var(--text-color); }
		.bg-guide .bg-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
		.bg-guide h2 { font-size: 21px; font-weight: 700; margin: 0 0 12px; line-height: 1.3; }
		.bg-guide .bg-lang { flex: none; display: inline-flex; border: 1px solid var(--border-color); border-radius: 999px; overflow: hidden; }
		.bg-guide .bg-lang button { border: 0; background: transparent; padding: 6px 16px; font-weight: 600; font-size: 13px; color: var(--text-muted); }
		.bg-guide .bg-lang button.active { background: #2563eb; color: #fff; }
		.bg-guide .bg-label { font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin: 0 0 8px; }
		.bg-guide .bg-flow { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 18px; }
		.bg-guide .bg-stage { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 999px;
			background: var(--control-bg, #f3f4f6); color: var(--text-muted); font-size: 12.5px; font-weight: 600; }
		.bg-guide .bg-stage .bg-n { font-size: 11px; opacity: .8; }
		.bg-guide .bg-stage.current { background: linear-gradient(135deg, #2563eb, #7c3aed); color: #fff;
			box-shadow: 0 3px 10px rgba(37, 99, 235, .35); }
		.bg-guide .bg-here { font-size: 10.5px; font-weight: 700; background: rgba(255,255,255,.25); border-radius: 999px; padding: 1px 7px; margin-left: 2px; }
		.bg-guide .bg-arrow { color: var(--text-light, #9ca3af); font-size: 13px; }
		.bg-guide .bg-purpose { background: #eff6ff; color: #1e3a8a; border-left: 4px solid #3b82f6; border-radius: 10px;
			padding: 12px 16px; margin-bottom: 20px; line-height: 1.6; }
		.bg-guide .bg-purpose .bg-label { color: #3b82f6; margin-bottom: 4px; }
		.bg-guide .bg-steps { list-style: none; margin: 0 0 18px; padding: 0; }
		.bg-guide .bg-step { position: relative; display: flex; gap: 14px; padding: 0 0 16px; }
		.bg-guide .bg-step:not(:last-child)::before { content: ""; position: absolute; left: 17px; top: 38px; bottom: 2px;
			width: 2px; background: linear-gradient(#c7d2fe, #e9d5ff); }
		.bg-guide .bg-num { flex: none; width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
			font-weight: 700; font-size: 15px; color: #fff; background: linear-gradient(135deg, #2563eb, #7c3aed);
			box-shadow: 0 2px 6px rgba(37, 99, 235, .3); }
		.bg-guide .bg-step h4 { margin: 7px 0 3px; font-size: 15px; font-weight: 650; color: var(--heading-color, var(--text-color)); }
		.bg-guide .bg-step p { margin: 0; color: var(--text-muted); line-height: 1.6; }
		.bg-guide .bg-step b, .bg-guide .bg-card b, .bg-guide .bg-next b { color: var(--text-color); font-weight: 650; }
		.bg-guide .bg-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
		@media (max-width: 720px) { .bg-guide .bg-cards { grid-template-columns: 1fr; } .bg-guide .bg-top { flex-direction: column-reverse; } }
		.bg-guide .bg-card { border-radius: 12px; padding: 13px 16px; border: 1px solid; }
		.bg-guide .bg-card ul { margin: 0; padding-left: 18px; }
		.bg-guide .bg-card li { margin: 4px 0; line-height: 1.55; }
		.bg-guide .bg-card.tips { background: #ecfdf3; border-color: #bbf7d0; color: #14532d; }
		.bg-guide .bg-card.avoid { background: #fff7ed; border-color: #fed7aa; color: #7c2d12; }
		.bg-guide .bg-card.tips b { color: #14532d; } .bg-guide .bg-card.avoid b { color: #7c2d12; }
		.bg-guide .bg-card .bg-label { color: inherit; opacity: .85; }
		.bg-guide .bg-next { display: flex; align-items: center; gap: 12px; margin-top: 16px; padding: 13px 16px; border-radius: 12px;
			background: linear-gradient(90deg, #eef2ff, #faf5ff); color: #3730a3; border: 1px solid #e0e7ff; line-height: 1.5; }
		.bg-guide .bg-next b { color: #3730a3; }
		.bg-guide .bg-next-tag { flex: none; font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
			background: #4f46e5; color: #fff; border-radius: 999px; padding: 3px 10px; }
	</style>`;

	const render = (key, lang) => {
		const guide = GUIDES[key];
		const text = guide[lang];
		const label = LABELS[lang];

		const flow = STAGES.map((stage, i) => {
			const current = guide.stages.includes(stage.key);
			const here = current && stage.key === guide.stages[0] ? `<span class="bg-here">${label.here}</span>` : "";
			return `<span class="bg-stage${current ? " current" : ""}">
					<span class="bg-n">${digits(i + 1, lang)}</span>${stage.icon} ${frappe.utils.escape_html(stage[lang])}${here}</span>`;
		}).join('<span class="bg-arrow">➜</span>');

		const steps = text.steps
			.map(
				([title, body], i) => `<li class="bg-step">
					<div class="bg-num">${digits(i + 1, lang)}</div>
					<div><h4>${rich(title)}</h4><p>${rich(body)}</p></div></li>`
			)
			.join("");
		const list = (items) => `<ul>${items.map((item) => `<li>${rich(item)}</li>`).join("")}</ul>`;

		return `${STYLE}<div class="bg-guide" lang="${lang}">
			<div class="bg-top">
				<h2>${rich(text.title)}</h2>
				<div class="bg-lang" role="group">
					<button type="button" data-lang="en" class="${lang === "en" ? "active" : ""}">English</button>
					<button type="button" data-lang="ne" class="${lang === "ne" ? "active" : ""}">नेपाली</button>
				</div>
			</div>
			<div class="bg-label">${label.flow}</div>
			<div class="bg-flow">${flow}</div>
			<div class="bg-purpose"><div class="bg-label">${label.purpose}</div>${rich(text.purpose)}</div>
			<div class="bg-label">${label.steps}</div>
			<ol class="bg-steps">${steps}</ol>
			<div class="bg-cards">
				<div class="bg-card tips"><div class="bg-label">💡 ${label.tips}</div>${list(text.tips)}</div>
				<div class="bg-card avoid"><div class="bg-label">⚠️ ${label.avoid}</div>${list(text.avoid)}</div>
			</div>
			<div class="bg-next"><span class="bg-next-tag">${label.next} ➜</span><span>${rich(text.next)}</span></div>
		</div>`;
	};

	const open = (key) => {
		if (!GUIDES[key]) return;
		const dialog = new frappe.ui.Dialog({
			title: "📘 Guide · मार्गदर्शन",
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "guide" }],
		});
		const $body = dialog.fields_dict.guide.$wrapper;
		const draw = (lang) => {
			$body.html(render(key, lang));
			$body.find(".bg-lang button").on("click", function () {
				const chosen = $(this).attr("data-lang");
				set_lang(chosen);
				draw(chosen);
			});
		};
		draw(get_lang());
		dialog.show();
		return dialog;
	};

	window.avinashgroup_app.buying_guide = { open, render, GUIDES, STAGES, BUTTON_LABEL };

	// The Guide button on each buying form
	const FORMS = {
		"Material Request": "mr",
		"Request for Quotation": "rfq",
		"Supplier Quotation": "sq",
		"Purchase Order": "po",
	};
	Object.entries(FORMS).forEach(([doctype, key]) => {
		frappe.ui.form.on(doctype, {
			refresh(frm) {
				frm.add_custom_button(BUTTON_LABEL, () => open(key));
			},
		});
	});
})();
