// Step-by-step guide, in English and Nepali, on every document of the purchase
// flow: Material Request -> (Request for Quotation, optional) -> Supplier
// Quotation -> comparison -> Purchase Order -> approval.
//
// Each form gets a "Guide" button. The guide has three sections:
//   1. What is this?  - the document, what it does, where it sits in the flow
//                       (RFQ drawn as optional, with the direct path beside it)
//                       and the fields that matter;
//   2. What to do     - numbered steps with a screenshot of the real screen;
//   3. What next      - buttons that make the next document from here, by
//                       pressing the form's own Create / Actions buttons.
//
// Loaded as doctype_js on the four buying forms (hooks.py) and by the Supplier
// Quotation Comparison report (frappe.require). The language choice is kept per
// browser. Screenshots live in public/images/buying_guide/.
(() => {
	window.avinashgroup_app = window.avinashgroup_app || {};
	if (window.avinashgroup_app.buying_guide) return; // already loaded by another form

	const LANG_KEY = "avinashgroup_buying_guide_lang";
	const BUTTON_LABEL = "📘 Guide / मार्गदर्शन";
	const SHOTS = "/assets/avinashgroup_app/images/buying_guide/";

	// The flow. RFQ is optional: a quotation can be made straight from the request.
	const STAGES = [
		{ key: "mr", icon: "📝", en: "Material Request", ne: "पर्चेज रिक्वेस्ट" },
		{ key: "rfq", icon: "📨", en: "RFQ", ne: "RFQ", optional: true },
		{ key: "sq", icon: "🧾", en: "Quotation", ne: "कोटेशन" },
		{ key: "compare", icon: "⚖️", en: "Compare", ne: "तुलना" },
		{ key: "po", icon: "📦", en: "Purchase Order", ne: "पर्चेज अर्डर" },
		{ key: "approve", icon: "✅", en: "Approval", ne: "एप्रुभल" },
	];

	const UI = {
		en: {
			tabs: ["What is this?", "What to do", "What next"],
			flow: "Where it fits",
			fields: "Fields that matter",
			steps: "Do this, step by step",
			tips: "Good to know",
			avoid: "Don't do this",
			make: "What you can do from here",
			here: "You are here",
			optional: "optional",
			bypass: "No RFQ? Make the quotation straight from the request",
			need_submit: "Submit this document first",
			not_now: "Not available at this stage",
			go: "Open",
			cont: "Continue",
			zoom: "Click the picture to see it bigger",
		},
		ne: {
			tabs: ["यो के हो?", "के गर्ने?", "अब के?"],
			flow: "प्रक्रियामा कहाँ पर्छ",
			fields: "मुख्य फिल्डहरू",
			steps: "यसरी गर्नुहोस्",
			tips: "थाहा पाउनुहोस्",
			avoid: "यस्तो नगर्नुहोस्",
			make: "यहाँबाट के गर्न सकिन्छ",
			here: "तपाईं यहाँ",
			optional: "अनिवार्य होइन",
			bypass: "RFQ चाहिँदैन? पर्चेज रिक्वेस्टबाट सिधै कोटेशन बनाउनुहोस्",
			need_submit: "पहिले यो कागज सबमिट गर्नुहोस्",
			not_now: "अहिले यो चरणमा उपलब्ध छैन",
			go: "खोल्नुहोस्",
			cont: "अगाडि",
			zoom: "ठूलो हेर्न तस्बिरमा क्लिक गर्नुहोस्",
		},
	};

	// How each "What next" card acts: press one of the form's own buttons, pick a
	// workflow action, or go somewhere. Returns a function, or null when it is not
	// available right now (the reason is shown instead).
	const act = {
		button: (label) => (frm) => {
			const btn = frm && frm.custom_buttons && frm.custom_buttons[__(label)];
			return btn ? () => btn.trigger("click") : null;
		},
		workflow: (label) => (frm) => {
			if (!frm) return null;
			const item = $(frm.page.wrapper)
				.find(".actions-btn-group .dropdown-menu a, .actions-btn-group .dropdown-menu .dropdown-item")
				.filter((_, el) => $(el).text().trim() === __(label))
				.first();
			return item.length ? () => item.trigger("click") : null;
		},
		comparison: () => (frm) => {
			const mr = material_request_of(frm);
			if (!frm || !mr) return null;
			return () => {
				frappe.route_options = {
					company: frm.doc.company,
					material_request: mr,
					purchase_order: [],
					from_date: "",
					to_date: "",
				};
				frappe.set_route("query-report", "Custom Supplier Quotation Comparison");
			};
		},
		back_to_request: () => (frm) => {
			const mr = material_request_of(frm);
			return frm && mr && frm.doctype !== "Material Request" ? () => frappe.set_route("Form", "Material Request", mr) : null;
		},
	};

	function material_request_of(frm) {
		if (!frm) return null;
		if (frm.doctype === "Material Request") return frm.doc.docstatus === 1 ? frm.doc.name : null;
		return (frm.doc.items || []).map((row) => row.material_request).find(Boolean) || null;
	}

	// **text** renders bold - the buttons and fields to look for on the screen.
	const GUIDES = {
		mr: {
			stages: ["mr"],
			en: {
				title: "Material Request",
				tagline: "Ask for what you need",
				about:
					"The request that says “we need these items”. It tells the purchase team which items, how many and by when. Every purchase starts here — nothing is bought without a submitted request.",
				fields: [
					["Required Miti", "the date you need the goods by"],
					["Branch", "your branch — the buying warehouse fills itself from it"],
					["Narration", "size, brand or anything the supplier must know"],
					["Vehicle", "which vehicle, for vehicle parts"],
				],
				steps: [
					["Fill in the main details", "Choose the **Company**, set the **Required Miti** and pick your **Branch**. Keep **Purpose** as **Purchase**.", "mr_basics"],
					["Add the items", "One line per item: **Item**, **Qty** and unit. Write size, brand or anything the supplier must know in **Narration**.", "mr_items"],
					["Save, then Submit", "Check the quantities once more, then **Save** and **Submit**. After submitting it can't be edited — if something is wrong, **Cancel** and **Amend** it."],
					["Ask for prices", "Open **Create**: choose **Request for Quotation** to ask several suppliers, or **Supplier Quotation** if a supplier has already given a price.", "mr_create"],
				],
				tips: [
					"The warehouse fills itself from the item and your branch — no need to type it.",
					"RFQ is optional. With one supplier, make the quotation straight away.",
				],
				avoid: [
					"Don't make a Purchase Order from here — this company buys only through quotations, so that button is hidden on purpose.",
					"Don't make a second request for the same items — **Cancel** and **Amend** the first one.",
				],
				actions: [
					{ icon: "📨", run: act.button("Request for Quotation"), tag: "Recommended", title: "Make an RFQ", text: "Ask 2–3 suppliers for prices in one go — best when you want to compare." },
					{ icon: "🧾", run: act.button("Supplier Quotation"), tag: "No RFQ", title: "Make a quotation directly", text: "A supplier has already given a price? Enter it straight away — RFQ is not needed." },
					{ icon: "⚖️", run: act.button("Supplier Quotation Comparison"), title: "See every quotation", text: "Compare all prices received for this request." },
				],
			},
			ne: {
				title: "पर्चेज रिक्वेस्ट",
				tagline: "चाहिने सामान माग्नुहोस्",
				about:
					"“हामीलाई यो सामान चाहियो” भनेर खरिद शाखालाई दिने माग हो। कुन आइटम, कति क्वान्टिटी र कहिलेसम्म चाहिने भन्ने यहीँ लेखिन्छ। हरेक खरिद यहीँबाट सुरु हुन्छ — सबमिट भएको रिक्वेस्ट बिना केही किनिँदैन।",
				fields: [
					["Required Miti", "सामान चाहिने मिति"],
					["Branch", "आफ्नो शाखा — गोदाम यसैबाट आफैँ भरिन्छ"],
					["Narration", "साइज, ब्रान्ड वा सप्लायरलाई भन्नुपर्ने कुरा"],
					["Vehicle", "गाडीको पार्टस भए कुन गाडी"],
				],
				steps: [
					["मुख्य विवरण भर्नुहोस्", "**Company** छान्नुहोस्, **Required Miti** राख्नुहोस् र आफ्नो **Branch** छान्नुहोस्। **Purpose** मा **Purchase** नै राख्नुहोस्।", "mr_basics"],
					["आइटम थप्नुहोस्", "हरेक लाइनमा एउटा आइटम: **Item**, **Qty** र युनिट। साइज, ब्रान्ड वा सप्लायरलाई भन्नुपर्ने कुरा **Narration** मा लेख्नुहोस्।", "mr_items"],
					["सेभ गरेर सबमिट गर्नुहोस्", "क्वान्टिटी एकपटक फेरि हेर्नुहोस्, अनि **Save** र **Submit** गर्नुहोस्। सबमिटपछि एडिट हुँदैन — गल्ती भए **Cancel** गरेर **Amend** गर्नुहोस्।"],
					["रेट माग्नुहोस्", "**Create** खोल्नुहोस्: धेरै सप्लायरसँग रेट माग्ने भए **Request for Quotation**, सप्लायरले रेट दिइसकेको भए सिधै **Supplier Quotation**।", "mr_create"],
				],
				tips: [
					"गोदाम आइटम र शाखाअनुसार आफैँ भरिन्छ — टाइप गर्नु पर्दैन।",
					"RFQ अनिवार्य होइन। एउटै सप्लायर भए सिधै कोटेशन बनाउनुहोस्।",
				],
				avoid: [
					"यहाँबाट पर्चेज अर्डर नबनाउनुहोस् — यो कम्पनीमा कोटेशन मार्फत मात्र खरिद हुन्छ, त्यसैले त्यो बटन जानाजानी लुकाइएको छ।",
					"उही आइटमका लागि अर्को रिक्वेस्ट नबनाउनुहोस् — पहिलेकोलाई **Cancel** गरेर **Amend** गर्नुहोस्।",
				],
				actions: [
					{ icon: "📨", run: act.button("Request for Quotation"), tag: "सिफारिस", title: "RFQ बनाउनुहोस्", text: "एकैचोटि २–३ सप्लायरसँग रेट माग्नुहोस् — तुलना गर्नुपर्दा यही राम्रो।" },
					{ icon: "🧾", run: act.button("Supplier Quotation"), tag: "RFQ बिना", title: "सिधै कोटेशन बनाउनुहोस्", text: "सप्लायरले रेट दिइसकेको छ? सिधै राख्नुहोस् — RFQ चाहिँदैन।" },
					{ icon: "⚖️", run: act.button("Supplier Quotation Comparison"), title: "सबै कोटेशन हेर्नुहोस्", text: "यो रिक्वेस्टका लागि आएका सबै रेट तुलना गर्नुहोस्।" },
				],
			},
		},

		rfq: {
			stages: ["rfq"],
			en: {
				title: "Request for Quotation (RFQ)",
				tagline: "Ask several suppliers for prices",
				about:
					"Sends the same item list to several suppliers, so everyone prices the same thing and you can compare fairly. It is optional — with only one supplier, make the quotation straight from the request.",
				fields: [
					["Suppliers", "everyone you want a price from"],
					["Required Miti", "when you need the prices by"],
					["Message for Supplier", "delivery place, terms, anything special"],
				],
				steps: [
					["Start from the request", "On the submitted Material Request press **Create ▸ Request for Quotation**. Items and quantities come across by themselves."],
					["Add the suppliers", "Add every supplier you want a price from — at least 2–3. If you will email it, check each has an email.", "rfq_suppliers"],
					["Date and message", "Set the **Required Miti** and write a short **Message for Supplier**."],
					["Save, Submit, send", "**Save** and **Submit**. Then **Tools ▸ Send Emails to Suppliers**, or **Download PDF** to hand it over."],
					["When a supplier replies", "Press **Create ▸ Supplier Quotation**, choose that supplier and enter the prices. One supplier = one quotation.", "rfq_create"],
				],
				tips: [
					"Keep the quantities the same as the request, so every supplier prices the same thing.",
					"Need one more supplier? **Amend** the RFQ and add them.",
				],
				avoid: [
					"Don't type the items by hand — start from the request so every document stays linked.",
					"Never put two suppliers' prices in one quotation.",
				],
				actions: [
					{ icon: "🧾", run: act.button("Supplier Quotation"), tag: "Next", title: "Make a quotation for a supplier", text: "A supplier sent prices? Pick them and enter their offer." },
					{ icon: "✉️", run: act.button("Send Emails to Suppliers"), title: "Email the RFQ", text: "Send this request to every supplier on the list." },
					{ icon: "📄", run: act.button("Download PDF"), title: "Download PDF", text: "Get the RFQ as a PDF for one supplier." },
				],
			},
			ne: {
				title: "RFQ (Request for Quotation)",
				tagline: "धेरै सप्लायरसँग रेट माग्नुहोस्",
				about:
					"एउटै आइटम लिस्ट धेरै सप्लायरलाई पठाउने कागज हो, ताकि सबैले एउटै कुराको रेट देऊन् र निष्पक्ष तुलना होस्। यो अनिवार्य होइन — एउटै सप्लायर भए पर्चेज रिक्वेस्टबाट सिधै कोटेशन बनाए पुग्छ।",
				fields: [
					["Suppliers", "रेट माग्ने सबै सप्लायर"],
					["Required Miti", "रेट चाहिने मिति"],
					["Message for Supplier", "डेलिभरी ठाउँ, सर्त वा विशेष कुरा"],
				],
				steps: [
					["रिक्वेस्टबाट सुरु गर्नुहोस्", "सबमिट भएको पर्चेज रिक्वेस्टमा **Create ▸ Request for Quotation** थिच्नुहोस्। आइटम र क्वान्टिटी आफैँ आउँछन्।"],
					["सप्लायर थप्नुहोस्", "रेट माग्ने सबै सप्लायर — कम्तीमा २–३ — थप्नुहोस्। इमेल पठाउने भए सप्लायरको इमेल छ कि हेर्नुहोस्।", "rfq_suppliers"],
					["मिति र सन्देश", "**Required Miti** राख्नुहोस् र छोटो **Message for Supplier** लेख्नुहोस्।"],
					["सेभ, सबमिट, पठाउनुहोस्", "**Save** र **Submit** गर्नुहोस्। अनि **Tools ▸ Send Emails to Suppliers**, वा हातैमा दिन **Download PDF**।"],
					["सप्लायरको रेट आएपछि", "**Create ▸ Supplier Quotation** थिच्नुहोस्, सप्लायर छान्नुहोस् र रेट राख्नुहोस्। एउटा सप्लायर = एउटा कोटेशन।", "rfq_create"],
				],
				tips: [
					"क्वान्टिटी रिक्वेस्ट जस्तै राख्नुहोस्, ताकि सबै सप्लायरले एउटै कुराको रेट देऊन्।",
					"अर्को सप्लायर चाहियो? RFQ लाई **Amend** गरेर थप्नुहोस्।",
				],
				avoid: [
					"आइटम हातले टाइप नगर्नुहोस् — रिक्वेस्टबाट सुरु गर्नुहोस्, ताकि सबै कागज जोडिएका रहून्।",
					"दुई सप्लायरको रेट एउटै कोटेशनमा कहिल्यै नराख्नुहोस्।",
				],
				actions: [
					{ icon: "🧾", run: act.button("Supplier Quotation"), tag: "अर्को", title: "सप्लायरको कोटेशन बनाउनुहोस्", text: "सप्लायरले रेट पठायो? सप्लायर छानेर रेट राख्नुहोस्।" },
					{ icon: "✉️", run: act.button("Send Emails to Suppliers"), title: "RFQ इमेल गर्नुहोस्", text: "लिस्टका सबै सप्लायरलाई यो रिक्वेस्ट पठाउनुहोस्।" },
					{ icon: "📄", run: act.button("Download PDF"), title: "PDF डाउनलोड", text: "एउटा सप्लायरका लागि RFQ को PDF लिनुहोस्।" },
				],
			},
		},

		sq: {
			stages: ["sq"],
			en: {
				title: "Supplier Quotation",
				tagline: "Enter one supplier's offer",
				about:
					"Records exactly what one supplier offered — rates, VAT, delivery and terms. The comparison is built from these quotations, so enter them as the supplier gave them.",
				fields: [
					["Rate / Qty", "the supplier's price, and their quantity if different"],
					["VAT, TDS, Excise", "set on each line, as on the supplier's paper"],
					["Preferred Quotation", "tick it so the offer shows in the comparison"],
					["Valid Miti", "until when the offer holds"],
				],
				steps: [
					["Where to make it", "From the RFQ: **Create ▸ Supplier Quotation**. No RFQ? From the Material Request: **Create ▸ Supplier Quotation**."],
					["Enter rates and VAT", "Type the **Rate** for each item and set **VAT Apply On / VAT Rate**, **TDS** and **Excise**. If the supplier offers a different quantity, change the **Qty**.", "sq_items"],
					["Terms and Preferred", "Fill **Specification**, **Warranty**, **Payment Terms**, **Delivery Period** and **Valid Miti**. Tick **Preferred Quotation** if this offer should be compared.", "sq_preferred"],
					["Save and Submit", "After **Submit** you are taken back to the Material Request to carry on."],
				],
				tips: [
					"Brand or model differs? Say so in the item's **Narration**.",
					"Attach the supplier's quotation paper or PDF here.",
				],
				avoid: [
					"Don't add VAT into the rate yourself — enter the rate as quoted and set the VAT on the line.",
					"Don't forget **Preferred Quotation** — otherwise the offer won't show in the comparison.",
				],
				actions: [
					{ icon: "📦", run: act.button("Purchase Order"), tag: "Chosen supplier", title: "Make the Purchase Order", text: "Only from the quotation you picked after comparing." },
					{ icon: "⚖️", run: act.comparison(), title: "Compare all quotations", text: "Open the comparison for this request." },
					{ icon: "↩️", run: act.back_to_request(), title: "Back to the request", text: "Return to the Material Request this quotation answers." },
				],
			},
			ne: {
				title: "सप्लायर कोटेशन",
				tagline: "एउटा सप्लायरको रेट राख्नुहोस्",
				about:
					"एउटा सप्लायरले दिएको रेट, भ्याट, डेलिभरी र सर्तहरूको रेकर्ड हो। तुलना यिनै कोटेशनबाट बन्छ, त्यसैले सप्लायरले दिए जस्तै ठ्याक्कै राख्नुहोस्।",
				fields: [
					["Rate / Qty", "सप्लायरको रेट, र क्वान्टिटी फरक भए त्यो पनि"],
					["VAT, TDS, Excise", "सप्लायरको कागज जस्तै हरेक लाइनमा"],
					["Preferred Quotation", "तुलनामा देखाउन टिक लगाउनुहोस्"],
					["Valid Miti", "कोटेशन कहिलेसम्म मान्य"],
				],
				steps: [
					["कहाँबाट बनाउने", "RFQ बाट: **Create ▸ Supplier Quotation**। RFQ छैन भने पर्चेज रिक्वेस्टबाट: **Create ▸ Supplier Quotation**।"],
					["रेट र भ्याट राख्नुहोस्", "हरेक आइटमको **Rate** राख्नुहोस्, र **VAT Apply On / VAT Rate**, **TDS**, **Excise** मिलाउनुहोस्। सप्लायरले फरक क्वान्टिटी दिएको भए **Qty** बदल्नुहोस्।", "sq_items"],
					["सर्त र Preferred", "**Specification**, **Warranty**, **Payment Terms**, **Delivery Period** र **Valid Miti** भर्नुहोस्। तुलनामा राख्ने भए **Preferred Quotation** मा टिक लगाउनुहोस्।", "sq_preferred"],
					["सेभ र सबमिट", "**Submit** गरेपछि तपाईं आफैँ पर्चेज रिक्वेस्टमा फर्किनुहुन्छ र काम त्यहीँबाट अगाडि बढ्छ।"],
				],
				tips: [
					"ब्रान्ड वा मोडल फरक छ? आइटमको **Narration** मा लेख्नुहोस्।",
					"सप्लायरको कोटेशन कागज वा PDF यहीँ Attach गर्नुहोस्।",
				],
				avoid: [
					"भ्याट आफैँ रेटभित्र नजोड्नुहोस् — रेट जस्तो दिएको छ त्यस्तै राख्नुहोस् र भ्याट लाइनमा राख्नुहोस्।",
					"**Preferred Quotation** टिक गर्न नबिर्सनुहोस् — नत्र तुलनामा देखिँदैन।",
				],
				actions: [
					{ icon: "📦", run: act.button("Purchase Order"), tag: "छानिएको सप्लायर", title: "पर्चेज अर्डर बनाउनुहोस्", text: "तुलनापछि छानेको कोटेशनबाट मात्र।" },
					{ icon: "⚖️", run: act.comparison(), title: "सबै कोटेशन तुलना गर्नुहोस्", text: "यो रिक्वेस्टको तुलना खोल्नुहोस्।" },
					{ icon: "↩️", run: act.back_to_request(), title: "रिक्वेस्टमा फर्किनुहोस्", text: "यो कोटेशन जुन पर्चेज रिक्वेस्टको हो, त्यहाँ जानुहोस्।" },
				],
			},
		},

		compare: {
			stages: ["compare"],
			en: {
				title: "Quotation Comparison",
				tagline: "Choose the best offer",
				about:
					"Every quotation for a Material Request side by side — what each supplier quoted, and what has already been ordered on Purchase Orders.",
				fields: [
					["MR Qty", "what the request asked for"],
					["Quoted", "the supplier's Qty, Rate and Amount — orange Qty means a different quantity"],
					["Ordered", "what Purchase Orders took from that quotation"],
					["Extend Purchase Order", "show each PO's own Qty, Rate and Amount"],
				],
				steps: [
					["Check the filters", "Opened from a request or order, the **Company** and **Material Request** are filled in for you. Tick **Extend Purchase Order** for the full PO detail.", "cmp_filters"],
					["Read the table", "Each coloured block is one quotation: **Quoted** then **Ordered**. Compare **Total**, **VAT**, **Invoice Amount** and the terms rows. **★** marks the order you opened from.", "cmp_grid"],
					["Print or export", "**Menu ▸ Print / PDF / Export** keeps the same layout for meetings and files."],
				],
				tips: [
					"Click a quotation or PO heading to open it.",
					"Untick **Preferred Quotation** to see every quotation, not only the preferred ones.",
				],
				avoid: [
					"A date range can hide quotations — opening from the request or order clears the dates for you.",
				],
				actions: [
					{ icon: "📦", run: () => null, tag: "Next", title: "Make the Purchase Order", text: "Click the chosen quotation's heading to open it, then **Create ▸ Purchase Order**." },
				],
			},
			ne: {
				title: "कोटेशन तुलना",
				tagline: "सबैभन्दा राम्रो रेट छान्नुहोस्",
				about:
					"एउटा पर्चेज रिक्वेस्टका सबै कोटेशन एकै ठाउँमा — कुन सप्लायरले के रेट दियो र पर्चेज अर्डरमा कति अर्डर भइसक्यो।",
				fields: [
					["MR Qty", "रिक्वेस्टमा मागेको क्वान्टिटी"],
					["Quoted", "सप्लायरको Qty, Rate र Amount — सुन्तला Qty भनेको फरक क्वान्टिटी"],
					["Ordered", "पर्चेज अर्डरले त्यो कोटेशनबाट लिएको"],
					["Extend Purchase Order", "हरेक PO को आफ्नै Qty, Rate र Amount देखाउने"],
				],
				steps: [
					["फिल्टर हेर्नुहोस्", "रिक्वेस्ट वा अर्डरबाट खोल्दा **Company** र **Material Request** आफैँ भरिन्छन्। PO को पूरा विवरण हेर्न **Extend Purchase Order** मा टिक लगाउनुहोस्।", "cmp_filters"],
					["टेबल पढ्नुहोस्", "हरेक रङीन ब्लक एउटा कोटेशन हो: पहिले **Quoted**, अनि **Ordered**। **Total**, **VAT**, **Invoice Amount** र सर्तहरू तुलना गर्नुहोस्। **★** ले तपाईंले खोलेको अर्डर जनाउँछ।", "cmp_grid"],
					["प्रिन्ट वा Export", "**Menu ▸ Print / PDF / Export** ले यही ढाँचामा फाइल दिन्छ — मिटिङ र फाइलका लागि।"],
				],
				tips: [
					"कोटेशन वा PO को शीर्षकमा क्लिक गर्दा त्यो खुल्छ।",
					"**Preferred Quotation** को टिक हटाए सबै कोटेशन देखिन्छन्।",
				],
				avoid: [
					"मितिको फिल्टरले कोटेशन लुकाउन सक्छ — रिक्वेस्ट वा अर्डरबाट खोल्दा मिति आफैँ हट्छ।",
				],
				actions: [
					{ icon: "📦", run: () => null, tag: "अर्को", title: "पर्चेज अर्डर बनाउनुहोस्", text: "छानेको कोटेशनको शीर्षकमा क्लिक गरेर खोल्नुहोस्, अनि **Create ▸ Purchase Order**।" },
				],
			},
		},

		po: {
			stages: ["po", "approve"],
			en: {
				title: "Purchase Order",
				tagline: "Order from the chosen supplier",
				about:
					"The official order to the supplier. It goes through approval and becomes final only when the last approver approves it.",
				fields: [
					["Department", "required — it decides who approves"],
					["Required By", "when the goods must arrive"],
					["Approval Hierarchy", "who will approve, level by level — set by itself"],
					["Approval History", "who approved, and when"],
				],
				steps: [
					["Make it from the chosen quotation", "On the quotation you picked, press **Create ▸ Purchase Order**. Supplier, items, rates and VAT come across — don't type them again.", "sq_create"],
					["Fill in the details", "**Department** (required), **Required By**, **Ship To** and **Note for Supplier**. Remove any item you are not buying from this supplier.", "po_details"],
					["Check the amounts", "Match **Value before VAT**, **VAT** and **TDS** with the quotation. Press **Supplier Quotation Comparison** to check once more.", "po_totals"],
					["Send for approval", "**Save**, then **Actions ▸ Submit for Approval**. The status becomes **Pending Approval** and the approver gets an email.", "po_actions"],
					["Approve or reject", "Approvers use **Actions ▸ Approve**, or **Reject** with a reason. After the last level it is **Approved** and final. Rejected? **Amend** it, fix it, send it again."],
				],
				tips: [
					"Ordered quantities show on the comparison as **Ordered 1, Ordered 2…**",
					"When the goods arrive, make a **Purchase Receipt** from this order.",
				],
				avoid: [
					"Don't make a Purchase Order from a blank form — start from the quotation so it stays linked.",
					"Don't change an order while it is **Pending Approval** unless asked — approvers would see the changed version.",
				],
				actions: [
					{ icon: "🚀", run: act.workflow("Submit for Approval"), tag: "Next", title: "Submit for Approval", text: "Send this order to the first approver." },
					{ icon: "⚖️", run: act.button("Supplier Quotation Comparison"), title: "Compare the quotations", text: "Check this order against every offer." },
					{ icon: "📥", run: act.button("Purchase Receipt"), title: "Make the Purchase Receipt", text: "After approval, when the goods arrive." },
				],
			},
			ne: {
				title: "पर्चेज अर्डर (PO)",
				tagline: "छानेको सप्लायरलाई अर्डर दिनुहोस्",
				about:
					"सप्लायरलाई दिने आधिकारिक अर्डर हो। यो एप्रुभलमा जान्छ र अन्तिम एप्रुभरले एप्रुभ गरेपछि मात्र फाइनल हुन्छ।",
				fields: [
					["Department", "अनिवार्य — कसले एप्रुभ गर्ने यसैले तय गर्छ"],
					["Required By", "सामान आइपुग्नुपर्ने मिति"],
					["Approval Hierarchy", "कसले कुन लेभलमा एप्रुभ गर्ने — आफैँ मिल्छ"],
					["Approval History", "कसले, कहिले एप्रुभ गर्‍यो"],
				],
				steps: [
					["छानेको कोटेशनबाट बनाउनुहोस्", "छानेको कोटेशनमा **Create ▸ Purchase Order** थिच्नुहोस्। सप्लायर, आइटम, रेट र भ्याट आफैँ आउँछन् — फेरि टाइप नगर्नुहोस्।", "sq_create"],
					["विवरण भर्नुहोस्", "**Department** (अनिवार्य), **Required By**, **Ship To** र **Note for Supplier** भर्नुहोस्। यो सप्लायरबाट नकिन्ने आइटम हटाउनुहोस्।", "po_details"],
					["रकम जाँच्नुहोस्", "**Value before VAT**, **VAT** र **TDS** कोटेशनसँग मिलाउनुहोस्। फेरि हेर्न **Supplier Quotation Comparison** थिच्नुहोस्।", "po_totals"],
					["एप्रुभलमा पठाउनुहोस्", "**Save** गरेर **Actions ▸ Submit for Approval** थिच्नुहोस्। स्टाटस **Pending Approval** हुन्छ र एप्रुभरलाई इमेल जान्छ।", "po_actions"],
					["एप्रुभ वा रिजेक्ट", "एप्रुभरले **Actions ▸ Approve** गर्छन्, वा कारण लेखेर **Reject**। अन्तिम लेभलपछि PO **Approved** भई फाइनल हुन्छ। रिजेक्ट भयो? **Amend** गरेर सच्याउनुहोस् र फेरि पठाउनुहोस्।"],
				],
				tips: [
					"अर्डर भएको क्वान्टिटी तुलनामा **Ordered 1, Ordered 2…** का रूपमा देखिन्छ।",
					"सामान आएपछि यही अर्डरबाट **Purchase Receipt** बनाउनुहोस्।",
				],
				avoid: [
					"खाली फारमबाट पर्चेज अर्डर नबनाउनुहोस् — कोटेशनबाट सुरु गर्नुहोस्, ताकि जोडिएको रहोस्।",
					"**Pending Approval** भएको अर्डर नभनिकन नबदल्नुहोस् — एप्रुभरले बदलिएको अर्डर देख्छन्।",
				],
				actions: [
					{ icon: "🚀", run: act.workflow("Submit for Approval"), tag: "अर्को", title: "एप्रुभलमा पठाउनुहोस्", text: "यो अर्डर पहिलो एप्रुभरलाई पठाउनुहोस्।" },
					{ icon: "⚖️", run: act.button("Supplier Quotation Comparison"), title: "कोटेशन तुलना गर्नुहोस्", text: "यो अर्डरलाई सबै रेटसँग दाँज्नुहोस्।" },
					{ icon: "📥", run: act.button("Purchase Receipt"), title: "पर्चेज रिसिट बनाउनुहोस्", text: "एप्रुभ भएपछि, सामान आइपुगेपछि।" },
				],
			},
		},
	};

	const NEPALI_DIGITS = "०१२३४५६७८९";
	const digits = (n, lang) => (lang === "ne" ? String(n).replace(/\d/g, (d) => NEPALI_DIGITS[d]) : String(n));
	const esc = (text) => frappe.utils.escape_html(text);
	const rich = (text) => esc(text).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");

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
		.bg-guide b { font-weight: 650; color: var(--heading-color, var(--text-color)); }

		/* hero */
		.bg-hero { display: flex; align-items: center; gap: 16px; padding: 18px 20px; border-radius: 16px; margin-bottom: 14px;
			background: #166534; color: #fff; }
		.bg-hero-icon { flex: none; width: 54px; height: 54px; border-radius: 14px; display: flex; align-items: center; justify-content: center;
			font-size: 28px; background: rgba(255,255,255,.18); box-shadow: inset 0 0 0 1px rgba(255,255,255,.25); }
		.bg-hero h2 { margin: 0; font-size: 22px; font-weight: 750; color: #fff; line-height: 1.25; }
		.bg-hero p { margin: 3px 0 0; font-size: 14px; color: rgba(255,255,255,.88); }
		.bg-hero .bg-lang { margin-left: auto; flex: none; display: inline-flex; background: rgba(255,255,255,.16); border-radius: 999px; padding: 3px; }
		.bg-hero .bg-lang button { border: 0; background: transparent; color: #fff; padding: 5px 14px; border-radius: 999px; font-weight: 600; font-size: 13px; }
		.bg-hero .bg-lang button.active { background: #fff; color: #166534; }

		/* tabs */
		.bg-tabs { display: flex; gap: 8px; margin-bottom: 18px; border-bottom: 1px solid var(--border-color); }
		.bg-tab { border: 0; background: transparent; padding: 10px 14px 12px; font-weight: 650; font-size: 14px; color: var(--text-muted);
			border-bottom: 3px solid transparent; margin-bottom: -1px; display: inline-flex; align-items: center; gap: 8px; }
		.bg-tab .bg-tab-n { width: 22px; height: 22px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
			font-size: 12px; background: var(--control-bg, #eef0f3); color: var(--text-muted); }
		.bg-tab.active { color: #166534; border-bottom-color: #16a34a; }
		.bg-tab.active .bg-tab-n { background: #15803d; color: #fff; }
		.bg-pane { display: none; } .bg-pane.active { display: block; }
		.bg-label { font-size: 11px; font-weight: 750; letter-spacing: .07em; text-transform: uppercase; color: var(--text-muted); margin: 0 0 10px; }

		/* 1 - what is this */
		.bg-about { font-size: 15px; line-height: 1.7; margin: 0 0 20px; }
		.bg-flowbox { border: 1px solid var(--border-color); border-radius: 14px; padding: 16px 16px 10px; margin-bottom: 20px; background: var(--card-bg, #fff); }
		.bg-flow { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 0; align-items: center; }
		.bg-node { position: relative; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 4px; padding: 0 4px; }
		/* connector to the next stage - not after the 6th, whose next sibling is the bypass line */
		.bg-node:not(:nth-child(6))::after { content: ""; position: absolute; top: 22px; left: calc(50% + 24px); right: calc(-50% + 24px);
			height: 2px; background: #cbd5e1; }
		.bg-dot { width: 44px; height: 44px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 20px;
			background: var(--control-bg, #f1f5f9); border: 2px solid #e2e8f0; z-index: 1; }
		.bg-node.optional .bg-dot { border-style: dashed; border-color: #94a3b8; }
		.bg-node.current .bg-dot { background: #15803d; border-color: transparent; color: #fff;
			box-shadow: 0 0 0 5px rgba(21, 128, 61, .16); }
		.bg-node-name { font-size: 12.5px; font-weight: 650; color: var(--text-color); line-height: 1.25; }
		.bg-node.current .bg-node-name { color: #166534; }
		.bg-chip { font-size: 10.5px; font-weight: 700; border-radius: 999px; padding: 1px 8px; }
		.bg-chip.here { background: #dcfce7; color: #166534; }
		.bg-chip.opt { background: #f1f5f9; color: #475569; border: 1px dashed #94a3b8; }
		.bg-bypass { grid-column: 1 / span 3; margin: 6px 22px 0; height: 22px; border: 2px dashed #86c49a; border-top: 0;
			border-radius: 0 0 14px 14px; position: relative; }
		.bg-bypass span { position: absolute; left: 50%; bottom: -11px; transform: translateX(-50%); white-space: nowrap;
			background: var(--card-bg, #fff); padding: 0 8px; font-size: 12px; font-weight: 600; color: #15803d; }
		.bg-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; }
		.bg-field { display: flex; gap: 10px; align-items: baseline; padding: 9px 12px; border-radius: 10px; background: var(--control-bg, #f8fafc); }
		.bg-field b { flex: none; }
		.bg-field span { color: var(--text-muted); line-height: 1.45; }

		/* 2 - what to do */
		.bg-steps { list-style: none; margin: 0 0 18px; padding: 0; }
		.bg-step { position: relative; display: flex; gap: 14px; padding: 0 0 20px; }
		.bg-step:not(:last-child)::before { content: ""; position: absolute; left: 17px; top: 40px; bottom: 4px; width: 2px;
			background: #bbf7d0; }
		.bg-num { flex: none; width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
			font-weight: 750; font-size: 15px; color: #fff; background: #15803d; box-shadow: 0 2px 6px rgba(21, 128, 61, .25); }
		.bg-step-body { flex: 1; min-width: 0; }
		.bg-step h4 { margin: 7px 0 4px; font-size: 15.5px; font-weight: 700; color: var(--heading-color, var(--text-color)); }
		.bg-step p { margin: 0; color: var(--text-muted); line-height: 1.65; }
		.bg-shot { margin: 10px 0 0; }
		.bg-shot img { display: block; max-width: 100%; max-height: 300px; border-radius: 10px; border: 1px solid var(--border-color);
			box-shadow: 0 6px 18px rgba(15, 23, 42, .10); cursor: zoom-in; background: #fff; }
		.bg-shot-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-start; }
		.bg-shot-row img { min-width: 0; flex: 1 1 280px; object-fit: contain; object-position: left top; }
		.bg-shot figcaption { font-size: 11.5px; color: var(--text-light, #94a3b8); margin-top: 5px; }
		.bg-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
		.bg-card { border-radius: 12px; padding: 13px 16px; border: 1px solid; }
		.bg-card ul { margin: 0; padding-left: 18px; } .bg-card li { margin: 4px 0; line-height: 1.55; }
		.bg-card.tips { background: #f0f9ff; border-color: #bae6fd; color: #0c4a6e; } .bg-card.tips b { color: #0c4a6e; }
		.bg-card.avoid { background: #fff7ed; border-color: #fed7aa; color: #7c2d12; } .bg-card.avoid b { color: #7c2d12; }
		.bg-card .bg-label { color: inherit; opacity: .9; }

		/* 3 - what next */
		.bg-actions { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }
		.bg-action { display: flex; flex-direction: column; gap: 8px; padding: 16px; border-radius: 14px; border: 1px solid var(--border-color);
			background: var(--card-bg, #fff); box-shadow: 0 1px 2px rgba(15,23,42,.04); }
		.bg-action-top { display: flex; align-items: center; gap: 10px; }
		.bg-action-icon { width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center; justify-content: center;
			font-size: 20px; background: #f0fdf4; }
		.bg-action h4 { margin: 0; font-size: 15px; font-weight: 700; color: var(--heading-color, var(--text-color)); }
		.bg-action .bg-chip { background: #dcfce7; color: #166534; margin-left: auto; }
		.bg-action p { margin: 0; color: var(--text-muted); line-height: 1.55; flex: 1; }
		.bg-action button { align-self: flex-start; border: 0; border-radius: 10px; padding: 8px 16px; font-weight: 650; font-size: 13.5px;
			color: #fff; background: #15803d; box-shadow: 0 2px 6px rgba(21, 128, 61, .25); }
		.bg-action button:hover { background: #166534; }
		.bg-action.off { background: var(--control-bg, #f8fafc); }
		.bg-action.off .bg-action-icon { background: #eef0f3; filter: grayscale(1); }
		.bg-action .bg-off { font-size: 12.5px; color: var(--text-light, #94a3b8); font-weight: 600; }

		.bg-foot { display: flex; justify-content: flex-end; margin-top: 18px; }
		.bg-foot button { border: 1px solid var(--border-color); background: var(--card-bg, #fff); border-radius: 10px; padding: 7px 16px;
			font-weight: 650; color: #166534; }
		@media (max-width: 760px) {
			.bg-fields, .bg-cards { grid-template-columns: 1fr; }
			.bg-flow { grid-template-columns: repeat(3, minmax(0, 1fr)); row-gap: 14px; }
			.bg-node:nth-child(3)::after, .bg-bypass { display: none; }
			.bg-hero { flex-wrap: wrap; } .bg-hero .bg-lang { margin-left: 0; }
		}
	</style>`;

	const render = (key, lang, frm, tab = 0) => {
		const guide = GUIDES[key];
		const text = guide[lang];
		const ui = UI[lang];
		const stage_icon = STAGES.find((s) => s.key === guide.stages[0]).icon;

		const tabs = ui.tabs
			.map((label, i) => `<button type="button" class="bg-tab${i === tab ? " active" : ""}" data-tab="${i}">
				<span class="bg-tab-n">${digits(i + 1, lang)}</span>${esc(label)}</button>`)
			.join("");

		// 1 - what is this
		const nodes = STAGES.map((stage) => {
			const current = guide.stages.includes(stage.key);
			const chip = current && stage.key === guide.stages[0]
				? `<span class="bg-chip here">${ui.here}</span>`
				: stage.optional ? `<span class="bg-chip opt">${ui.optional}</span>` : "";
			return `<div class="bg-node${current ? " current" : ""}${stage.optional ? " optional" : ""}">
				<div class="bg-dot">${stage.icon}</div>
				<div class="bg-node-name">${esc(stage[lang])}</div>${chip}</div>`;
		}).join("");
		const fields = text.fields
			.map(([name, meaning]) => `<div class="bg-field"><b>${esc(name)}</b><span>${esc(meaning)}</span></div>`)
			.join("");
		const pane_about = `
			<p class="bg-about">${rich(text.about)}</p>
			<div class="bg-label">${ui.flow}</div>
			<div class="bg-flowbox">
				<div class="bg-flow">${nodes}<div class="bg-bypass"><span>↪ ${esc(ui.bypass)}</span></div></div>
			</div>
			<div class="bg-label">${ui.fields}</div>
			<div class="bg-fields">${fields}</div>`;

		// 2 - what to do
		// A step shows one screenshot, or several side by side (shot = key or [keys]).
		const shots_html = (shot) => {
			if (!shot) return "";
			const imgs = (Array.isArray(shot) ? shot : [shot])
				.map((name) => `<img src="${SHOTS}${name}.webp" alt="" loading="lazy" data-full="${SHOTS}${name}.webp">`)
				.join("");
			return `<figure class="bg-shot"><div class="bg-shot-row">${imgs}</div><figcaption>${ui.zoom}</figcaption></figure>`;
		};
		const steps = text.steps
			.map(([title, body, shot], i) => `<li class="bg-step">
				<div class="bg-num">${digits(i + 1, lang)}</div>
				<div class="bg-step-body"><h4>${rich(title)}</h4><p>${rich(body)}</p>${shots_html(shot)}</div></li>`)
			.join("");
		const list = (items) => `<ul>${items.map((item) => `<li>${rich(item)}</li>`).join("")}</ul>`;
		const pane_steps = `
			<div class="bg-label">${ui.steps}</div>
			<ol class="bg-steps">${steps}</ol>
			<div class="bg-cards">
				<div class="bg-card tips"><div class="bg-label">💡 ${ui.tips}</div>${list(text.tips)}</div>
				<div class="bg-card avoid"><div class="bg-label">⚠️ ${ui.avoid}</div>${list(text.avoid)}</div>
			</div>`;

		// 3 - what next
		const actions = text.actions
			.map((action, i) => {
				const run = action.run(frm);
				// No frm (the report page): the card is advice only, no button or note.
				const status = run
					? `<button type="button" data-action="${i}">${ui.go} ➜</button>`
					: !frm ? ""
					: frm.doc.docstatus === 0 ? `<span class="bg-off">🔒 ${ui.need_submit}</span>`
					: `<span class="bg-off">${ui.not_now}</span>`;
				return `<div class="bg-action${run ? "" : " off"}">
					<div class="bg-action-top"><div class="bg-action-icon">${action.icon}</div><h4>${esc(action.title)}</h4>
						${action.tag ? `<span class="bg-chip">${esc(action.tag)}</span>` : ""}</div>
					<p>${rich(action.text)}</p>${status}</div>`;
			})
			.join("");
		const pane_next = `<div class="bg-label">${ui.make}</div><div class="bg-actions">${actions}</div>`;

		const panes = [pane_about, pane_steps, pane_next]
			.map((html, i) => `<div class="bg-pane${i === tab ? " active" : ""}" data-pane="${i}">${html}</div>`)
			.join("");

		return `${STYLE}<div class="bg-guide" lang="${lang}">
			<div class="bg-hero">
				<div class="bg-hero-icon">${stage_icon}</div>
				<div><h2>${esc(text.title)}</h2><p>${esc(text.tagline)}</p></div>
				<div class="bg-lang" role="group">
					<button type="button" data-lang="en" class="${lang === "en" ? "active" : ""}">English</button>
					<button type="button" data-lang="ne" class="${lang === "ne" ? "active" : ""}">नेपाली</button>
				</div>
			</div>
			<div class="bg-tabs">${tabs}</div>
			${panes}
			<div class="bg-foot"><button type="button" class="bg-continue">${ui.cont} ➜</button></div>
		</div>`;
	};

	const open = (key, frm) => {
		if (!GUIDES[key]) return;
		const dialog = new frappe.ui.Dialog({
			title: "📘 Guide · मार्गदर्शन",
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "guide" }],
		});
		const $body = dialog.fields_dict.guide.$wrapper;
		let lang = get_lang();
		let tab = 0;

		const show_tab = (i) => {
			tab = i;
			$body.find(".bg-tab").removeClass("active").filter(`[data-tab="${i}"]`).addClass("active");
			$body.find(".bg-pane").removeClass("active").filter(`[data-pane="${i}"]`).addClass("active");
			$body.find(".bg-continue").toggle(i < 2);
		};
		const draw = () => {
			$body.html(render(key, lang, frm, tab));
			show_tab(tab);
			$body.find(".bg-lang button").on("click", function () {
				lang = $(this).attr("data-lang");
				set_lang(lang);
				draw();
			});
			$body.find(".bg-tab").on("click", function () {
				show_tab(parseInt($(this).attr("data-tab")));
			});
			$body.find(".bg-continue").on("click", () => show_tab(Math.min(tab + 1, 2)));
			$body.find(".bg-shot img").on("click", function () {
				window.open($(this).attr("data-full"), "_blank");
			});
			$body.find(".bg-action button").on("click", function () {
				const run = GUIDES[key][lang].actions[parseInt($(this).attr("data-action"))].run(frm);
				dialog.hide();
				if (run) run();
			});
		};
		draw();
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
				frm.add_custom_button(BUTTON_LABEL, () => open(key, frm));
			},
		});
	});
})();
