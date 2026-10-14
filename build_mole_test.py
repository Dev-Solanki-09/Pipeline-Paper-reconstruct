"""
Build script for 'mole and redox Test -2 (1).pdf'.
Reconstructs the first 25 questions with numbering from 26 to 50.
Produces a 50/50 bilingual continuous HTML file and saves run artifacts.
"""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path
from PIL import Image

from examforge.config import ExamForgeConfig
from examforge.ir.schema import (
    BBox,
    Block,
    BlockStatus,
    BlockType,
    ExamDocument,
    ExamMetadata,
    Figure,
    FigureClass,
    Lang,
    Option,
    PageClassification,
    PageInfo,
    Question,
    QuestionKind,
)
from examforge.orchestrator.runner import RunDirectory
from examforge.spec import Spec
from examforge.stages.base import StageContext
from examforge.stages.s8_verify import S8Verify
from examforge.stages.s9_package import S9Package


def build_paper():
    root = Path(__file__).parent.resolve()
    pdf_path = root / "sample_papers" / "mole_and_redox_test_2.pdf"
    if not pdf_path.exists():
        pdf_path = root / "mole and redox Test -2 (1).pdf"
    output_dir = root / "runs" / "mole_and_redox_test_2"
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # 1. Prepare Pyridine ring figure for Question 37 (original Q12)
    pyridine_src = root / "sample_papers" / "mole_pages" / "pyridine_ring.png"
    if not pyridine_src.exists():
        page2_img = root / "sample_papers" / "mole_pages" / "page_2.png"
        img = Image.open(page2_img)
        w, h = img.size
        crop = img.crop((int(w * 0.165), int(h * 0.805), int(w * 0.225), int(h * 0.865)))
        crop.save(pyridine_src)

    pyridine_dest = figures_dir / "pyridine_ring.png"
    shutil.copy(pyridine_src, pyridine_dest)
    pyr_b64 = base64.b64encode(pyridine_dest.read_bytes()).decode("ascii")
    pyr_img_tag = f'<img src="data:image/png;base64,{pyr_b64}" class="img-opt" alt="Pyridine structure" style="max-height: 52px; vertical-align: middle; width: auto;">'

    # 2. Build Questions (26 through 50)
    questions: list[Question] = [
        # Q26 (Original 1)
        Question(
            id="q26",
            number=26,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="20 litres of H₂ gas at S.T.P. weigh about.",
            stem_text_hi="S.T.P. पर H₂ गैस के 20 लीटर का भार लगभग है",
            options=[
                Option(label="1", text_str_en="12.2 g", text_str_hi="12.2 g"),
                Option(label="2", text_str_en="448 g", text_str_hi="448 g"),
                Option(label="3", text_str_en="1.8 g", text_str_hi="1.8 g"),
                Option(label="4", text_str_en="20 g", text_str_hi="20 g"),
            ],
            source_pages=[1],
        ),
        # Q27 (Original 2)
        Question(
            id="q27",
            number=27,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="For combustion of 10 ml mixture of methane (CH₄) and propane (C₃H₈), 41 ml O₂ is required then composition of mixture is -",
            stem_text_hi="मेथेन (CH₄) तथा प्रोपेन (C₃H₈) के 10 ml मिश्रण के दहन के लिए 41 ml O₂ की आवश्यकता होती है तो मिश्रण का संगठन होगा-",
            options=[
                Option(label="1", text_str_en="3 ml CH₄ + 9 ml C₃H₈", text_str_hi="3 ml CH₄ + 9 ml C₃H₈"),
                Option(label="2", text_str_en="5 ml CH₄ + 5 ml C₃H₈", text_str_hi="5 ml CH₄ + 5 ml C₃H₈"),
                Option(label="3", text_str_en="3 ml CH₄ + 7 ml C₃H₈", text_str_hi="3 ml CH₄ + 7 ml C₃H₈"),
                Option(label="4", text_str_en="1 ml CH₄ + 9 ml C₃H₈", text_str_hi="1 ml CH₄ + 9 ml C₃H₈"),
            ],
            source_pages=[1],
        ),
        # Q28 (Original 3)
        Question(
            id="q28",
            number=28,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="Which of the following oxides of nitrogen have 30.5% nitrogen -",
            stem_text_hi="निम्न में से कौनसे नाइट्रोजन के ऑक्साइड में 30.5% nitrogen है -",
            options=[
                Option(label="1", text_str_en="NO", text_str_hi="NO"),
                Option(label="2", text_str_en="NO₂", text_str_hi="NO₂"),
                Option(label="3", text_str_en="N₂O₃", text_str_hi="N₂O₃"),
                Option(label="4", text_str_en="N₂O₅", text_str_hi="N₂O₅"),
            ],
            source_pages=[1],
        ),
        # Q29 (Original 4)
        Question(
            id="q29",
            number=29,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="20 g of an ideal gas contains only atoms of S and O occupies 5.6 L at 1 atm and 273 K. What is the mole weight of gas -",
            stem_text_hi="सल्फर तथा ऑक्सीजन परमाणुओं से बनी एक आदर्श गैस के 20 g का 1 atm तथा 273 K पर आयतन 5.6 L है। गैस का मोलर द्रव्यमान होगा -",
            options=[
                Option(label="1", text_str_en="64", text_str_hi="64"),
                Option(label="2", text_str_en="80", text_str_hi="80"),
                Option(label="3", text_str_en="96", text_str_hi="96"),
                Option(label="4", text_str_en="None", text_str_hi="कोई नहीं"),
            ],
            source_pages=[1],
        ),
        # Q30 (Original 5)
        Question(
            id="q30",
            number=30,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="80 gram of NH₄NO₂ gives 16.8 Ltr of N₂(g) at STP on complete decomposition. Percentage purity of NH₄NO₂ will be -",
            stem_text_hi="80 ग्राम, NH₄NO₂ के पूर्ण विघटन से STP पर 16.8 लीटर N₂(g) मुक्त होती है। NH₄NO₂ की प्रतिशत शुद्धता होगी -",
            options=[
                Option(label="1", text_str_en="40%", text_str_hi="40%"),
                Option(label="2", text_str_en="60%", text_str_hi="60%"),
                Option(label="3", text_str_en="75%", text_str_hi="75%"),
                Option(label="4", text_str_en="90%", text_str_hi="90%"),
            ],
            source_pages=[1],
        ),
        # Q31 (Original 6)
        Question(
            id="q31",
            number=31,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="A mixture of gases contains CH₄ and O₂ gases in the ratio 1 : 4 (w/w). What is the molar ratio of the two gases in the mixture -",
            stem_text_hi="एक गैस के मिश्रण में CH₄ तथा O₂ गैस का अनुपात 1 : 4 (w/w) है। मिश्रण में इन दोनों गैसों का मोलर अनुपात है -",
            options=[
                Option(label="1", text_str_en="16 : 1", text_str_hi="16 : 1"),
                Option(label="2", text_str_en="8 : 1", text_str_hi="8 : 1"),
                Option(label="3", text_str_en="1 : 2", text_str_hi="1 : 2"),
                Option(label="4", text_str_en="1 : 4", text_str_hi="1 : 4"),
            ],
            source_pages=[1],
        ),
        # Q32 (Original 7)
        Question(
            id="q32",
            number=32,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="The number of moles of CaCO₃ which contains 5.4 moles of oxygen atoms is -",
            stem_text_hi="CaCO₃ के मोलो की संख्या जिसमें 5.4 मोल ऑक्सीजन परमाणु है -",
            options=[
                Option(label="1", text_str_en="0.9", text_str_hi="0.9"),
                Option(label="2", text_str_en="1.8", text_str_hi="1.8"),
                Option(label="3", text_str_en="2.7", text_str_hi="2.7"),
                Option(label="4", text_str_en="5.4", text_str_hi="5.4"),
            ],
            source_pages=[2],
        ),
        # Q33 (Original 8)
        Question(
            id="q33",
            number=33,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="74.5 g of a metallic chloride contains 35.5 g of chlorine. The equivalent mass of the metal is -",
            stem_text_hi="74.5 g धात्विक क्लोराइड में 35.5 g क्लोरीन हैं। धातु का तुल्यांकी भार है -",
            options=[
                Option(label="1", text_str_en="19.5", text_str_hi="19.5"),
                Option(label="2", text_str_en="35.5", text_str_hi="35.5"),
                Option(label="3", text_str_en="39.0", text_str_hi="39.0"),
                Option(label="4", text_str_en="78.0", text_str_hi="78.0"),
            ],
            source_pages=[2],
        ),
        # Q34 (Original 9)
        Question(
            id="q34",
            number=34,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="H₃PO₄ can be neutralised by NaOH, Ca(OH)₂ and Al(OH)₃. The required mole of each for 1 equivalent of H₃PO₄ are in ratio -",
            stem_text_hi="H₃PO₄ का उदासीनीकरण NaOH, Ca(OH)₂ तथा Al(OH)₃ द्वारा होता है। H₃PO₄ के 1 तुल्यांक के लिए प्रत्येक के आवश्यक मोल का अनुपात होगा-",
            options=[
                Option(label="1", text_str_en="1 : 1 : 1", text_str_hi="1 : 1 : 1"),
                Option(label="2", text_str_en="1 : 0.5 : 0.33", text_str_hi="1 : 0.5 : 0.33"),
                Option(label="3", text_str_en="1 : 2 : 3", text_str_hi="1 : 2 : 3"),
                Option(label="4", text_str_en="2 : 3 : 6", text_str_hi="2 : 3 : 6"),
            ],
            source_pages=[2],
        ),
        # Q35 (Original 10)
        Question(
            id="q35",
            number=35,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="Which of the following relation is correct -",
            stem_text_hi="निम्न में से कौनसा सम्बन्ध सही है-",
            options=[
                Option(label="1", text_str_en="Molar mass of gas = 2 × vapour density", text_str_hi="गैस का मोलर द्रव्यमान = 2 × वाष्प घनत्व"),
                Option(label="2", text_str_en="Normality = Molarity × Valency factor of solute", text_str_hi="नॉर्मलता = मोलरता × विलेय का संयोजकता कारक"),
                Option(label="3", text_str_en="Molar mass = Equivalent weight × Valency factor", text_str_hi="मोलर द्रव्यमान = तुल्यांकी भार × संयोजकता कारक"),
                Option(label="4", text_str_en="All of these", text_str_hi="उपरोक्त सभी"),
            ],
            source_pages=[2],
        ),
        # Q36 (Original 11)
        Question(
            id="q36",
            number=36,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="Cl₂ changes to Cl⁻ and ClO⁻ in cold NaOH. Equivalent weight of Cl₂ will be-",
            stem_text_hi="Cl₂ ठण्डे NaOH में Cl⁻ व ClO⁻ में परिवर्तित होता है। Cl₂ का तुल्यांकी भार होगा-",
            options=[
                Option(label="1", text_str_en="M", text_str_hi="M"),
                Option(label="2", text_str_en="M/2", text_str_hi="M/2"),
                Option(label="3", text_str_en="M/3", text_str_hi="M/3"),
                Option(label="4", text_str_en="2M/3", text_str_hi="2M/3"),
            ],
            source_pages=[2],
        ),
        # Q37 (Original 12)
        Question(
            id="q37",
            number=37,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="For which of the following Kjeldahl's method is applicable-",
            stem_text_hi="निम्न में से किस के लिए कैल्डॉल विधि लागू होती है-",
            options=[
                Option(label="1", text_str_en="CH₃ – NO₂", text_str_hi="CH₃ – NO₂"),
                Option(label="2", text_str_en="CH₃ – N = N – C₂H₅", text_str_hi="CH₃ – N = N – C₂H₅"),
                Option(label="3", text_str_en="C₆H₅NH₂", text_str_hi="C₆H₅NH₂"),
                Option(label="4", text_str_en=pyr_img_tag, text_str_hi=pyr_img_tag, figure_ref="fig_pyridine"),
            ],
            figure_refs=[],
            source_pages=[2],
        ),
        # Q38 (Original 13)
        Question(
            id="q38",
            number=38,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="0.2 litre of hydrocarbon on complete combustion produces 800 ml CO₂(g) and 1000 ml of H₂O(g). The hydrocarbon is -",
            stem_text_hi="0.2 लीटर हाइड्रोकार्बन का पूर्ण दहन करने पर 800 ml CO₂(g) तथा 1000 ml, H₂O(g) गैस देता है, तो हाइड्रोकार्बन है-",
            options=[
                Option(label="1", text_str_en="C₄H₅", text_str_hi="C₄H₅"),
                Option(label="2", text_str_en="C₈H₁₀", text_str_hi="C₈H₁₀"),
                Option(label="3", text_str_en="C₄H₈", text_str_hi="C₄H₈"),
                Option(label="4", text_str_en="C₄H₁₀", text_str_hi="C₄H₁₀"),
            ],
            source_pages=[3],
        ),
        # Q39 (Original 14)
        Question(
            id="q39",
            number=39,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="An organic compound contains 40% carbon and 6.67% hydrogen by mass. Which of the following represents the empirical formula of the compound-",
            stem_text_hi="एक कार्बनिक यौगिक 40% कार्बन तथा 6.67% हाइड्रोजन भार रूप में रखता है, तो निम्न में से कौनसा यौगिक के मूलानुपाती सूत्र को प्रदर्शित करता है-",
            options=[
                Option(label="1", text_str_en="CH₂", text_str_hi="CH₂"),
                Option(label="2", text_str_en="CH₂O", text_str_hi="CH₂O"),
                Option(label="3", text_str_en="C₂H₄O", text_str_hi="C₂H₄O"),
                Option(label="4", text_str_en="CH₃O", text_str_hi="CH₃O"),
            ],
            source_pages=[3],
        ),
        # Q40 (Original 15)
        Question(
            id="q40",
            number=40,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="Number of significant figures present in $1.34 \\times 10^{-2}$ are -",
            stem_text_hi="$1.34 \\times 10^{-2}$ में सार्थक अंकों की संख्या है",
            options=[
                Option(label="1", text_str_en="Zero", text_str_hi="शून्य"),
                Option(label="2", text_str_en="2", text_str_hi="2"),
                Option(label="3", text_str_en="3", text_str_hi="3"),
                Option(label="4", text_str_en="5", text_str_hi="5"),
            ],
            source_pages=[3],
        ),
        # Q41 (Original 16)
        Question(
            id="q41",
            number=41,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en=(
                "Sulphur trioxide is prepared by the following two reactions\n"
                "$$\\text{S}_8(\\text{s}) + 8\\text{O}_2(\\text{g}) \\rightarrow 8\\text{SO}_2(\\text{g})$$\n"
                "$$2\\text{SO}_2(\\text{g}) + \\text{O}_2(\\text{g}) \\rightarrow 2\\text{SO}_3(\\text{g})$$\n"
                "How many grams of SO₃ are produced from 1 mol of S₈?"
            ),
            stem_text_hi=(
                "सल्फर ट्राई ऑक्साइड निम्न दो अभिक्रियाओं से बनता है।\n"
                "$$\\text{S}_8(\\text{s}) + 8\\text{O}_2(\\text{g}) \\rightarrow 8\\text{SO}_2(\\text{g})$$\n"
                "$$2\\text{SO}_2(\\text{g}) + \\text{O}_2(\\text{g}) \\rightarrow 2\\text{SO}_3(\\text{g})$$\n"
                "S₈ के 1 मोल से कितने ग्राम SO₃ बनेगी ?"
            ),
            options=[
                Option(label="1", text_str_en="1280.0", text_str_hi="1280.0"),
                Option(label="2", text_str_en="640.0", text_str_hi="640.0"),
                Option(label="3", text_str_en="960.0", text_str_hi="960.0"),
                Option(label="4", text_str_en="320.0", text_str_hi="320.0"),
            ],
            source_pages=[4],
        ),
        # Q42 (Original 17)
        Question(
            id="q42",
            number=42,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="If 0.5 mol of BaCl₂ is mixed with 0.1 mole of Na₃PO₄, the maximum number of mole of Ba₃(PO₄)₂ that can be formed is :",
            stem_text_hi="यदि BaCl₂ के 0.5 मोल को Na₃PO₄ के 0.1 मोल के साथ मिश्रित किया गया, तो बनने वाले Ba₃(PO₄)₂ के अधिकतम मोलों की संख्या है :",
            options=[
                Option(label="1", text_str_en="0.7", text_str_hi="0.7"),
                Option(label="2", text_str_en="0.05", text_str_hi="0.05"),
                Option(label="3", text_str_en="0.30", text_str_hi="0.30"),
                Option(label="4", text_str_en="0.10", text_str_hi="0.10"),
            ],
            source_pages=[4],
        ),
        # Q43 (Original 18)
        Question(
            id="q43",
            number=43,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="4 g of hydrogen is ignited with 4 g of oxygen, the amount of water formed is ?",
            stem_text_hi="4 g ऑक्सीजन के साथ 4 g हाइड्रोजन को प्रज्ज्वलित किया जाता है तो उत्पादित जल की मात्रा निम्न है ?",
            options=[
                Option(label="1", text_str_en="2.5 g", text_str_hi="2.5 g"),
                Option(label="2", text_str_en="0.5 g", text_str_hi="0.5 g"),
                Option(label="3", text_str_en="4.5 g", text_str_hi="4.5 g"),
                Option(label="4", text_str_en="8 g", text_str_hi="8 g"),
            ],
            source_pages=[4],
        ),
        # Q44 (Original 19)
        Question(
            id="q44",
            number=44,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="The molarity of the solution containing 2.8% mass-volume solution of KOH is",
            stem_text_hi="उस विलयन की मोलरता क्या होगी जो KOH का 2.8% (द्रव्यमान-आयतन) रखता हो।",
            options=[
                Option(label="1", text_str_en="M/10", text_str_hi="M/10"),
                Option(label="2", text_str_en="M/2", text_str_hi="M/2"),
                Option(label="3", text_str_en="M/5", text_str_hi="M/5"),
                Option(label="4", text_str_en="1 M", text_str_hi="1 M"),
            ],
            source_pages=[4],
        ),
        # Q45 (Original 20)
        Question(
            id="q45",
            number=45,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="300 ml of 3.0 M NaCl is added to 200 ml of 4.0 M BaCl₂ solution. The concentration of Cl⁻ ions in the resulting solution is",
            stem_text_hi="3.0 M NaCl विलयन के 300 ml को 4.0 M BaCl₂ विलयन के 200 ml के साथ मिलाया जाता है। परिणामी विलयन में Cl⁻ आयन की सान्द्रता निम्न है :",
            options=[
                Option(label="1", text_str_en="7 M", text_str_hi="7 M"),
                Option(label="2", text_str_en="1.6 M", text_str_hi="1.6 M"),
                Option(label="3", text_str_en="1.8 M", text_str_hi="1.8 M"),
                Option(label="4", text_str_en="5 M", text_str_hi="5 M"),
            ],
            source_pages=[4],
        ),
        # Q46 (Original 21)
        Question(
            id="q46",
            number=46,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="If one mole of ethanol (C₂H₅OH) completely burns to form carbon dioxide and water, the weight of carbon dioxide formed is about -",
            stem_text_hi="यदि एक मोल एथेनॉल (C₂H₅OH) पूर्ण रूप से जलकर कार्बन डाईऑक्साइड तथा जल देता है तो बनी कार्बन डाईऑक्साइड का भार है -",
            options=[
                Option(label="1", text_str_en="22 gm", text_str_hi="22 gm"),
                Option(label="2", text_str_en="45 gm", text_str_hi="45 gm"),
                Option(label="3", text_str_en="66 gm", text_str_hi="66 gm"),
                Option(label="4", text_str_en="88 gm", text_str_hi="88 gm"),
            ],
            source_pages=[4],
        ),
        # Q47 (Original 22)
        Question(
            id="q47",
            number=47,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en=(
                "The moles of O₂ required for reacting with 6.8 gm of ammonia.\n"
                "$$(\\dots\\dots \\text{NH}_3 + \\dots\\dots \\text{O}_2 \\rightarrow \\dots\\dots \\text{NO} + \\dots\\dots \\text{H}_2\\text{O})\\text{ is}$$"
            ),
            stem_text_hi=(
                "6.8 ग्राम अमोनिया से क्रिया करने के लिये ऑक्सीजन के कितने मोल की आवश्यकता है-\n"
                "$$(\\dots\\dots \\text{NH}_3 + \\dots\\dots \\text{O}_2 \\rightarrow \\dots\\dots \\text{NO} + \\dots\\dots \\text{H}_2\\text{O})$$"
            ),
            options=[
                Option(label="1", text_str_en="5", text_str_hi="5"),
                Option(label="2", text_str_en="2.5", text_str_hi="2.5"),
                Option(label="3", text_str_en="1", text_str_hi="1"),
                Option(label="4", text_str_en="0.5", text_str_hi="0.5"),
            ],
            source_pages=[4],
        ),
        # Q48 (Original 23)
        Question(
            id="q48",
            number=48,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="What mass of calcium chloride in grams would be enough to produce 14.35 gm of AgCl. (At. mass Ca = 40, Ag = 108) -",
            stem_text_hi="14.35 ग्राम AgCl बनाने के लिये कितने ग्राम CaCl₂ की आवश्यकता होगी (परमाणु भार Ca = 40, Ag = 108) -",
            options=[
                Option(label="1", text_str_en="5.55 gm", text_str_hi="5.55 gm"),
                Option(label="2", text_str_en="8.295 gm", text_str_hi="8.295 gm"),
                Option(label="3", text_str_en="16.59 gm", text_str_hi="16.59 gm"),
                Option(label="4", text_str_en="11.19 gm", text_str_hi="11.19 gm"),
            ],
            source_pages=[4],
        ),
        # Q49 (Original 24)
        Question(
            id="q49",
            number=49,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="1.35 gm of pure Ca metal was quantitatively converted into 1.88 gm of pure CaO. What is atomic weight of Ca -",
            stem_text_hi="यदि 1.35 ग्राम शुद्ध Ca धातु को 1.88 ग्राम CaO में परिवर्तित कर दिया जाता है तो Ca का परमाणु भार कितना होगा-",
            options=[
                Option(label="1", text_str_en="40.75", text_str_hi="40.75"),
                Option(label="2", text_str_en="50", text_str_hi="50"),
                Option(label="3", text_str_en="60", text_str_hi="60"),
                Option(label="4", text_str_en="70", text_str_hi="70"),
            ],
            source_pages=[4],
        ),
        # Q50 (Original 25)
        Question(
            id="q50",
            number=50,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="If V ml of the vapours of substance at NTP weight W g. Then mol w. of substance is :",
            stem_text_hi="यदि NTP पर एक पदार्थ के V ml वाष्प का भार W g है, तो पदार्थ का अणुभार है :",
            options=[
                Option(label="1", text_str_en="(W/V) × 22400", text_str_hi="(W/V) × 22400"),
                Option(label="2", text_str_en="(V/W) × 22.4", text_str_hi="(V/W) × 22.4"),
                Option(label="3", text_str_en="(W – V) × 22400", text_str_hi="(W – V) × 22400"),
                Option(label="4", text_str_en="$\\frac{\\text{W} \\times 1}{\\text{V} \\times 22400}$", text_str_hi="$\\frac{\\text{W} \\times 1}{\\text{V} \\times 22400}$"),
            ],
            source_pages=[5],
        ),
    ]

    # Set sequence_index and original_number explicitly
    for idx, q in enumerate(questions, start=1):
        q.original_number = idx
        q.sequence_index = idx

    # 3. Create Figure objects
    figures: list[Figure] = [
        Figure(
            id="fig_pyridine",
            page=2,
            bbox=BBox(x1=204, y1=1412, x2=279, y2=1518),
            crop_path="figures/pyridine_ring.png",
            format="png",
            classification=FigureClass.DIAGRAM,
            scale_class="img-sm",
            question_ref="q37",
            option_ref="4",
        )
    ]

    # 4. Create Pages
    pages: list[PageInfo] = [
        PageInfo(page_number=i, classification=PageClassification.QUESTIONS)
        for i in range(1, 6)
    ]

    # 5. Assemble ExamDocument
    doc = ExamDocument(
        source_path=str(pdf_path),
        source_hash="mole_redox_test_2_hash",
        metadata=ExamMetadata(
            exam_name="MOLE CONCEPT & REDOX REACTIONS — TEST - 2",
            subject="CHEMISTRY",
            year=2025,
            total_questions=25,
        ),
        pages=pages,
        questions=questions,
        figures=figures,
    )

    # 6. Verification with S8Verify
    config = ExamForgeConfig(paths={"runs": root / "runs"})
    spec = Spec.default()
    ctx = StageContext(
        document=doc,
        config=config,
        spec=spec,
        stage_dir=output_dir / "s8_verify",
        run_dir=output_dir,
    )

    verifier = S8Verify()
    verify_result = verifier.run(ctx)
    print(f"Verification completed. Issues found: {len(verify_result.issues)}")
    for issue in verify_result.issues:
        print(f"  [{issue.severity.value}] {issue.id}: {issue.message}")

    # 7. Packaging with S9Package
    pkg_ctx = StageContext(
        document=doc,
        config=config,
        spec=spec,
        stage_dir=output_dir / "s9_package",
        run_dir=output_dir,
    )
    packager = S9Package()
    packager.run(pkg_ctx)

    # 8. Copy to accessible destination files
    generated_html = output_dir / "output.html"
    root_output_html = root / "mole_and_redox_test_2_q26_50.html"
    shutil.copy(generated_html, root_output_html)

    print("\nSUCCESS!")
    print(f"Generated HTML: {root_output_html}")
    print(f"Run directory: {output_dir}")
    print(f"Total questions: {len(questions)} (Q{questions[0].number} to Q{questions[-1].number})")


if __name__ == "__main__":
    build_paper()
