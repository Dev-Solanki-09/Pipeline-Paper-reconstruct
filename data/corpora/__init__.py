"""Seed corpora for ExamForge synthetic generator."""

EN_QUESTIONS = [
    {
        "stem": "An ideal gas expands isothermally from volume V1 to V2 at temperature T. The work done by the gas is given by:",
        "options": ["W = nRT ln(V2/V1)", "W = nRT (V2 - V1)", "W = nRT ln(V1/V2)", "W = 0"],
        "subject": "Physics",
        "topic": "Thermodynamics",
    },
    {
        "stem": "A particle moves in a circle of radius R with constant speed v. The magnitude of its average acceleration over a quarter revolution is:",
        "options": ["2*sqrt(2)*v^2 / (pi*R)", "v^2 / R", "2*v^2 / (pi*R)", "sqrt(2)*v^2 / R"],
        "subject": "Physics",
        "topic": "Kinematics",
    },
    {
        "stem": "Which of the following compounds exhibits optical isomerism?",
        "options": ["2-chlorobutane", "1-chlorobutane", "2-chloropropane", "1-chloropropane"],
        "subject": "Chemistry",
        "topic": "Organic Chemistry",
    },
    {
        "stem": "The oxidation state of chromium in K2Cr2O7 is:",
        "options": ["+6", "+3", "+7", "+4"],
        "subject": "Chemistry",
        "topic": "Inorganic Chemistry",
    },
    {
        "stem": "During DNA replication, the discontinuous synthesis of DNA occurs on which strand?",
        "options": ["Lagging strand only", "Leading strand only", "Both strands", "Neither strand"],
        "subject": "Biology",
        "topic": "Genetics",
    },
    {
        "stem": "The organelle responsible for ATP synthesis via oxidative phosphorylation is:",
        "options": ["Mitochondria", "Chloroplast", "Golgi apparatus", "Endoplasmic reticulum"],
        "subject": "Biology",
        "topic": "Cell Biology",
    },
    {
        "stem": "If matrix A is orthogonal, then the value of det(A) is:",
        "options": ["+1 or -1", "0", "Always +1", "Any real number"],
        "subject": "Mathematics",
        "topic": "Linear Algebra",
    },
    {
        "stem": "The value of the limit as x approaches 0 of sin(3x)/x is:",
        "options": ["3", "1", "0", "1/3"],
        "subject": "Mathematics",
        "topic": "Calculus",
    },
]

HI_QUESTIONS = [
    {
        "stem": "एक आदर्श गैस तापमान T पर आयतन V1 से V2 तक समतापी रूप से प्रसारित होती है। गैस द्वारा किया गया कार्य है:",
        "options": ["W = nRT ln(V2/V1)", "W = nRT (V2 - V1)", "W = nRT ln(V1/V2)", "W = 0"],
    },
    {
        "stem": "एक कण त्रिज्या R के वृत्त में स्थिर चाल v से गति करता है। एक-चौथाई चक्कर में इसके औसत त्वरण का परिमाण है:",
        "options": ["2*sqrt(2)*v^2 / (pi*R)", "v^2 / R", "2*v^2 / (pi*R)", "sqrt(2)*v^2 / R"],
    },
    {
        "stem": "निम्नलिखित में से कौन-सा यौगिक प्रकाशिक समावयवता प्रदर्शित करता है?",
        "options": ["2-क्लोरोब्यूटेन", "1-क्लोरोब्यूटेन", "2-क्लोरोप्रोपेन", "1-क्लोरोप्रोपेन"],
    },
    {
        "stem": "K2Cr2O7 में क्रोमियम की ऑक्सीकरण अवस्था है:",
        "options": ["+6", "+3", "+7", "+4"],
    },
    {
        "stem": "डीएनए प्रतिकृति के दौरान, डीएनए का असतत संश्लेषण किस रज्जुक पर होता है?",
        "options": ["केवल पश्चगामी रज्जुक पर", "केवल अग्रगामी रज्जुक पर", "दोनों रज्जुकों पर", "किसी भी रज्जुक पर नहीं"],
    },
    {
        "stem": "ऑक्सीडेटिव फॉस्फारिलीकरण के माध्यम से एटीपी संश्लेषण के लिए जिम्मेदार कोशिकांग है:",
        "options": ["माइटोकॉन्ड्रिया", "क्लोरोप्लास्ट", "गॉल्जी उपकरण", "अंतर्द्रव्यी जालिका"],
    },
    {
        "stem": "यदि आव्यूह A लाम्बिक है, तो det(A) का मान है:",
        "options": ["+1 या -1", "0", "सदैव +1", "कोई भी वास्तविक संख्या"],
    },
    {
        "stem": "x के 0 की ओर अग्रसर होने पर sin(3x)/x की सीमा का मान है:",
        "options": ["3", "1", "0", "1/3"],
    },
]

MATCH_ITEMS = [
    {
        "left": [("A", "Chloroplast"), ("B", "Mitochondria"), ("C", "Ribosome"), ("D", "Lysosome")],
        "right": [("I", "Protein synthesis"), ("II", "Photosynthesis"), ("III", "Hydrolytic enzymes"), ("IV", "Cellular respiration")],
        "left_hi": [("A", "क्लोरोप्लास्ट"), ("B", "माइटोकॉन्ड्रिया"), ("C", "राइबोसोम"), ("D", "लाइसोसोम")],
        "right_hi": [("I", "प्रोटीन संश्लेषण"), ("II", "प्रकाश संश्लेषण"), ("III", "जलअपघटनीय एंजाइम"), ("IV", "कोशिकीय श्वसन")],
        "correct": "A-II, B-IV, C-I, D-III",
    },
    {
        "left": [("A", "Ohm's Law"), ("B", "Faraday's Law"), ("C", "Coulomb's Law"), ("D", "Ampere's Law")],
        "right": [("I", "Electromagnetic induction"), ("II", "Electrostatic force"), ("III", "Magnetic field of current"), ("IV", "V = IR")],
        "left_hi": [("A", "ओम का नियम"), ("B", "फैराडे का नियम"), ("C", "कूलॉम का नियम"), ("D", "एम्पीयर का नियम")],
        "right_hi": [("I", "विद्युतचुंबकीय प्रेरण"), ("II", "स्थिरवैद्युत बल"), ("III", "धारा का चुंबकीय क्षेत्र"), ("IV", "V = IR")],
        "correct": "A-IV, B-I, C-II, D-III",
    },
]

ASSERTION_REASON_PAIRS = [
    {
        "assertion_en": "Assertion (A): The boiling point of water decreases at higher altitudes.",
        "reason_en": "Reason (R): Atmospheric pressure decreases with increasing altitude.",
        "assertion_hi": "अभिकथन (A): अधिक ऊंचाई पर जल का क्वथनांक कम हो जाता है।",
        "reason_hi": "कारण (R): ऊंचाई बढ़ने के साथ वायुमंडलीय दबाव कम हो जाता है।",
        "options_en": [
            "Both (A) and (R) are true and (R) is the correct explanation of (A).",
            "Both (A) and (R) are true but (R) is NOT the correct explanation of (A).",
            "(A) is true but (R) is false.",
            "(A) is false but (R) is true.",
        ],
        "options_hi": [
            "(A) और (R) दोनों सही हैं और (R), (A) की सही व्याख्या है।",
            "(A) और (R) दोनों सही हैं लेकिन (R), (A) की सही व्याख्या नहीं है।",
            "(A) सही है लेकिन (R) गलत है।",
            "(A) गलत है लेकिन (R) सही है।",
        ],
    }
]

PASSAGES = [
    {
        "stem_en": "Read the following passage and answer the questions that follow:\nA photoelectric experiment is conducted using radiation of frequency f incident on a metal surface of work function W0. The maximum kinetic energy of the emitted photoelectrons is measured to be Kmax.",
        "stem_hi": "निम्नलिखित गद्यांश को पढ़कर दिए गए प्रश्नों के उत्तर दीजिए:\nकार्य फलन W0 वाली एक धातु की सतह पर आवृत्ति f का विकिरण आपतित कराकर एक प्रकाश विद्युत प्रयोग किया जाता है। उत्सर्जित फोटोइलेक्ट्रॉनों की अधिकतम गतिज ऊर्जा Kmax मापी जाती है।",
        "questions": [
            {
                "stem_en": "According to Einstein's photoelectric equation, the relationship between Kmax, f, and W0 is:",
                "stem_hi": "आइंस्टीन के प्रकाश विद्युत समीकरण के अनुसार, Kmax, f और W0 के बीच संबंध है:",
                "options_en": ["Kmax = hf - W0", "Kmax = hf + W0", "Kmax = W0 - hf", "Kmax = hf / W0"],
                "options_hi": ["Kmax = hf - W0", "Kmax = hf + W0", "Kmax = W0 - hf", "Kmax = hf / W0"],
            },
            {
                "stem_en": "If the incident frequency is doubled, the stopping potential will:",
                "stem_hi": "यदि आपतित आवृत्ति को दोगुना कर दिया जाए, तो निरोधी विभव:",
                "options_en": ["Become more than double", "Become exactly double", "Remain unchanged", "Become half"],
                "options_hi": ["दोगुने से अधिक हो जाएगा", "ठीक दोगुना हो जाएगा", "अपरिवर्तित रहेगा", "आधा हो जाएगा"],
            },
        ],
    }
]
