"""Pipeline stages: the processing units that transform the ExamDocument."""

from examforge.stages.base import Stage, StageContext, StageResult
from examforge.stages.s0_intake import S0Intake
from examforge.stages.s1_profile import S1Profile
from examforge.stages.s2_clean import S2Clean
from examforge.stages.s3_parse import S3Parse
from examforge.stages.s4_structure import S4Structure
from examforge.stages.s5_hindi import S5Hindi
from examforge.stages.s5_math import S5Math
from examforge.stages.s5_normalize import S5Normalize
from examforge.stages.s6_figures import S6Figures
from examforge.stages.s7_repair import S7Repair
from examforge.stages.s8_verify import S8Verify
from examforge.stages.s9_package import S9Package

__all__ = [
    "Stage",
    "StageContext",
    "StageResult",
    "S0Intake",
    "S1Profile",
    "S2Clean",
    "S3Parse",
    "S4Structure",
    "S5Hindi",
    "S5Math",
    "S5Normalize",
    "S6Figures",
    "S7Repair",
    "S8Verify",
    "S9Package",
]
