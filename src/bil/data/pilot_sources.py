"""Pinned input snapshots for the private NBA possession builds, one season at a time."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import file_digest
from pathlib import Path
from typing import NotRequired, TypedDict, cast
from urllib.request import urlopen

ARCHIVE_REVISION = "46488f0f8e1cab58fc1256511ea808166a443a15"
ARCHIVE_BASE = f"https://raw.githubusercontent.com/shufinskiy/nba_data/{ARCHIVE_REVISION}/datasets"
BOX_BASE = "https://basketball-data.billmill.org/nba/stats"
BENTES_BASE = "https://github.com/ramirobentes/nba_data/releases/download"
RIGHTS_REF = "nba-stats-private-noncommercial-pilot"
ATTRIBUTION = "NBA.com (NBA game statistics)"
NBA_TERMS = "https://www.nba.com/termsofuse"

# Seasons are keyed by starting year, so 2023 means 2023–24. Shufinskiy names files by starting
# year, while Bill Mill and Bentes use the ending year. 2025–26 is the confirmatory holdout
# governed by issue #42. It has no pins here, so it cannot be captured, loaded or built.
HOLDOUT_START_YEAR = 2025
# NBA liveData play-by-play, the only archive feed that may be absent for a pinned season.
LIVEDATA = "cdnnba"


@dataclass(frozen=True)
class Source:
    name: str
    uri: str
    sha256: str
    size_bytes: int
    publisher: str
    revision: str | None = None
    # Basename in a local audit capture, when it differs from the snapshot name.
    local_name: str | None = None


# Shufinskiy archive digests and sizes, as recorded in the issue #51 coverage register.
_ARCHIVE_PINS: dict[int, dict[str, tuple[str, int]]] = {
    2017: {
        "nbastats": (
            "efd8c7139acb737ebdc76e0b98b118cb6152caffc0077cf2c7b6ef25a580e50f",
            8_361_064,
        ),
        "nbastats_po": (
            "a01469513826024a01a84c112ae01ddc79fc5829cf013f5f43395aa850aa81a2",
            544_912,
        ),
        "nbastatsv3": (
            "e9fedc33337e6a34dc4373bc5138e742e6bbcf09477b34568d79588dead7e62c",
            8_371_044,
        ),
        "nbastatsv3_po": (
            "e12f876c8f17e44775941440ac936c018a3d7a20fc6740697ef3a7719ed2fa7e",
            554_416,
        ),
        "shotdetail": (
            "a62d25aa9c9190477f350f06a9a2d808c7908a6720786970319a3b28af184e81",
            2_719_384,
        ),
        "shotdetail_po": (
            "1a0ede5238ae0d165980e7b90d01998a34f93f3f94dfa3abb5e63135c9307a00",
            181_436,
        ),
        "datanba": (
            "14a2a3ceb56cef387d61dbb794bd94899343bee79bd21201bf9e2c6c18ec1707",
            8_938_852,
        ),
        "datanba_po": (
            "9172db6e1317d100877dac23e16ef0057a016c64f6e7cd95e98927114c62a0bc",
            588_388,
        ),
        "pbpstats": (
            "214e5f4e0f0608b49ea90eccaf101ac1bf221fbba07db6e7ea954e47071d366e",
            16_631_168,
        ),
        "pbpstats_po": (
            "45c11741a3649dfdf076b8c3a1ae43ddf43999a92f46d082a90fcb37fdd4898e",
            1_082_008,
        ),
    },
    2018: {
        "nbastats": (
            "b5416e7d270011970e7934de0cabb41cf75c16f48b34c2b035e1a96760faa407",
            8_705_484,
        ),
        "nbastats_po": (
            "1ca4fe50e6a06c8857bb4a3bfb54452b4a20fbabc1fcef095c2f984358bac5f5",
            566_480,
        ),
        "nbastatsv3": (
            "a8c05607863b0bb0da51ed65fc89866cbb5c1954f7951ce00ed05f2ad178097d",
            8_680_224,
        ),
        "nbastatsv3_po": (
            "8e63c35c64b666599a74602b9156dd9eac5440160d950bea83b31d8bef3d0685",
            578_480,
        ),
        "shotdetail": (
            "c658890976559b69dff44ed08352baf64b935514506e726d21f34950ad5bfe9d",
            2_814_056,
        ),
        "shotdetail_po": (
            "78e544cafb228c8d198fd6c55f16617ac746c7a343f14bb6df47a233028aaace",
            187_400,
        ),
        "datanba": (
            "3bf2e855a594f8d9bc6e29515bb9ea5b0cd6c26ececf2832e4fb27c92053c856",
            9_358_052,
        ),
        "datanba_po": (
            "708fa511b5f330224d0450d5fc09164690b993a6e068708c1e30cd187b9bce09",
            618_304,
        ),
        "pbpstats": (
            "a691620a095f74736d157a6a0d5db1f52d54a994dbd7c0089f1c35d5e15e5547",
            17_085_516,
        ),
        "pbpstats_po": (
            "a4fab2be0b8990fbe70c3ea4056b264bcd73e2b3c6172d2eaa452d2d3536ce3a",
            1_125_188,
        ),
    },
    2019: {
        "nbastats": (
            "06c53b6e42be2698dbbf550260f46f9ca51ad495fb8e9964a0c24473a3fe7064",
            7_504_672,
        ),
        "nbastats_po": (
            "888a4227769cd9f519fb110223b757f33e02759f853735b5d02ddca3ec911731",
            558_696,
        ),
        "nbastatsv3": (
            "3fc651e4c294e231723fa097dca2cf938dd868ee2b9a6111f22ab9c0728e89dc",
            7_529_968,
        ),
        "nbastatsv3_po": (
            "f0e09f0815e489f1735914426a240e5b647dc7e0ca1812cdde39846e830970c1",
            574_464,
        ),
        "shotdetail": (
            "0c6002cbc8bc379ecc0a2e0f57defb2e9804be8240aa0234242002ec5dd124fe",
            2_417_916,
        ),
        "shotdetail_po": (
            "9d2a6772c09012033101e3e70d6584cc3d97894b156bbb3c5979dfa66a045411",
            185_492,
        ),
        "datanba": (
            "6b0801fdef9b3486dedccf8f3f86bdfae128f01e7421bd6a05b79df72766af5f",
            8_070_912,
        ),
        "datanba_po": (
            "cd0eeb81e076b191c6aeb9bd2dae6ff05eb4bba004b6987ebbe21d5c45ba3bde",
            611_808,
        ),
        "pbpstats": (
            "68c8f6a37c6c61ba9927a705d6fb9662bec8065da6b853fafac5472248223c56",
            14_453_712,
        ),
        "pbpstats_po": (
            "3d4b0c5a830967308170ef23678be6d9d0661a29e4571e1f50a91c1347487767",
            1_022_016,
        ),
    },
    2020: {
        "nbastats": (
            "40a1126ecf66c4068c994d9a207040d0a62e40bd4634949f9b199b86bf5e79af",
            7_493_576,
        ),
        "nbastats_po": (
            "b92b6f95d534970a18285b888540ac87bcffb8bf29da9be49e943e891f74cf33",
            566_280,
        ),
        "nbastatsv3": (
            "8bbd2406d741f8247db9eec222bb1655ea699edb60907d3851a048b8ea7a798d",
            7_511_996,
        ),
        "nbastatsv3_po": (
            "dca8358956e9b91ee47ffc562c446e212e228dc1071fdd201e4101325ab4e46f",
            585_440,
        ),
        "shotdetail": (
            "02916ac0a4a0c8dcb1e115ed08ddb49b360305f98f4882c8933a2998b747487d",
            2_456_200,
        ),
        "shotdetail_po": (
            "d57f0075849a208ae2dc10e88016e0c7196c348d525929063dc07f2908dc4aa6",
            194_744,
        ),
        "cdnnba": (
            "e45e1b4a70a33ce93525c58f04362b6c275f7e514789772d4a8360f22a13f4f2",
            15_548_680,
        ),
        "cdnnba_po": (
            "b2e04db1d6a9110241152871adb4787b758a1cc4c1fbe55650830593f2bc9322",
            1_183_336,
        ),
        "datanba": (
            "224aa9b4ed3436d0d98dfbe9933ae9d6994802cee4870e89568a20db2de147b0",
            8_069_236,
        ),
        "datanba_po": (
            "5825e12cfc4298c3cf2cff12488b70285f9d3603a209b9a094bd81b9a2f75d1e",
            609_860,
        ),
        "pbpstats": (
            "a582a23f93f6fcd110b7dac4a42e297d81cfe3c42c2ab0bc67275978f420e130",
            13_679_676,
        ),
        "pbpstats_po": (
            "7146ed14ca82f38cd714a871bf26a1078c396febaa3ca8ac36389739ad11f087",
            1_043_160,
        ),
    },
    2021: {
        "nbastats": (
            "549915410733f799f61ff54c18b69185138f61f462b9f82b8c17dd5777de3780",
            8_575_520,
        ),
        "nbastats_po": (
            "693f67747102576b0f80cc005b5c68d8e108c12b8523162ce06c4e09d5314281",
            580_896,
        ),
        "nbastatsv3": (
            "f44ec8a4a9864732fca66943ae4d06a06ef98ba3932571c15a23ecae644f84c4",
            8_567_128,
        ),
        "nbastatsv3_po": (
            "8ce37e2144c61b482a5ee4e6386d7ce9f15bde1d1c25b919b6db985505e3754f",
            593_612,
        ),
        "shotdetail": (
            "5b56b6833d179fdef9c76223064c7923717b1add83570becf494a3f1d0a785f2",
            2_791_576,
        ),
        "shotdetail_po": (
            "ca4b2fbecd3f7de3a9a7c80798cb21146fd78e4da03eabcc85de743197015fc4",
            192_084,
        ),
        "cdnnba": (
            "0c116aff50b829de70902023f108ee78c0f44bec569521ebf1fa292e01bda28f",
            17_660_924,
        ),
        "cdnnba_po": (
            "942eee56d0afba2b0b3934d0d3eff93d85a56f7889abc12f58ea1ec5705f4afa",
            1_199_840,
        ),
        "datanba": (
            "f7a900e058b5941456160105bde035240133219354f5b4540b7398760a3a8e4c",
            9_196_044,
        ),
        "datanba_po": (
            "1289d417d10bd8eeb03885640a17fcfbf4e01aaf270af8890216aa8386f41072",
            636_936,
        ),
        "pbpstats": (
            "e9969cd6b5c00e42ae93307a8aa577322be67f38a8bfd60143747ea509cc4e6c",
            15_615_952,
        ),
        "pbpstats_po": (
            "fcbd9d69d458fcb45ea23a57451b4cd4cca0bc8c2bdfb50b9c7a6fa34936daa6",
            1_051_588,
        ),
    },
    2022: {
        "nbastats": ("46fead1357db9d1e56ed8158c820fe8e65e12c444151448c4e225889296629d0", 8_551_312),
        "nbastats_po": (
            "512c600cb21b8fce1b123cf709c07e10902d7893eb3185a6f5ebe93db0447c87",
            559_312,
        ),
        "nbastatsv3": (
            "42c24abf0abbc0ccef00addaba4b8c76df230a0ff3c0e5b301353307941fd04c",
            8_640_724,
        ),
        "nbastatsv3_po": (
            "de43f41ac4ce2d7a579b5cd933f980e5413313ec8b5da734cc9c36d1bbb2bb3f",
            573_940,
        ),
        "shotdetail": (
            "62533f4e444ef0fc3354cdf6bbc04e249eb14ba9f444e6cd247c3e95d235e46d",
            2_792_344,
        ),
        "shotdetail_po": (
            "9e3137fd28b590d8c7a446c286500fc01d786e483b51fcc85f461d5a89cdbe37",
            193_132,
        ),
        "cdnnba": ("de895e3474365fc14b028f514eb0f8c9c1503b95d3f1a5aef5a408305ddfb41f", 18_705_272),
        "cdnnba_po": (
            "2f20055f6d7d54fdc74fb910ef8db0901166fca3a701a2a4f50448af3a32298c",
            1_218_416,
        ),
        "datanba": ("8be05e5ae4b598b115ecfed8d4c9cef5cd324a21d6383bd8dd185401f2ebbf69", 11_310_412),
        "datanba_po": ("b112928125780366f9b4dc40c06d480b64e738d8b3c797a37de91eb87a1540ba", 743_948),
        "pbpstats": (
            "a4847be1f5adeda20453b14cfcd7e67aaffb85398b00bdacd15ae00b3f91d710",
            15_206_248,
        ),
        "pbpstats_po": (
            "5f7cf15db7978cd553871e884253a6c69d981ad840e9b2261d828c0e514802c3",
            1_033_288,
        ),
    },
    2023: {
        "nbastats": ("ec0029c0d45a90b769d173010f60b73c6c8866acf1d4d914a72476373ce3a913", 8_480_776),
        "nbastats_po": (
            "8fce0780f0a3aaec00b84b93457edd8562cc34ccaa64a01db2f193f0048de8bb",
            536_072,
        ),
        "nbastatsv3": (
            "3a6976219b87fb50cecf8b2c54cb2af110f2f013ed8368d694035806802c8b04",
            8_622_472,
        ),
        "nbastatsv3_po": (
            "7ea0923674e736051a97c6d4e6726913564a225d800947b25b8d27f0e3eb672b",
            549_760,
        ),
        "shotdetail": (
            "303e71f967c199568b345cd73a75e595f1f99532cca3e6ce59afb286b63f840d",
            2_812_692,
        ),
        "shotdetail_po": (
            "36d6a1794c2003ae7ca4a27978956fd0385aa2619d4e35f2b32637554191fdb4",
            183_112,
        ),
        "cdnnba": ("33d49fefc809f73d5d6cbad6d1d6690e0df6c89fe2b5a4d814ecc9ea4df6101b", 18_598_380),
        "cdnnba_po": (
            "5c347769636d136504a3ccb028417333edc7a67ead0aba7e61ba5bf6cc304685",
            1_160_972,
        ),
        "datanba": ("c82be81e532b3cc023a5646ca427e2ca35812f96f1e685ee0b743aba1839bc1e", 11_196_452),
        "datanba_po": ("1198adbf2c849aa3868e7e17804840cbc9f8b91f37916ef108f44c2f2219c128", 710_044),
        "pbpstats": (
            "c4eff1692da05ec83094a056aa8d773fe7965f3d0aa7c01d1b3dd5f50a0e3fe8",
            15_029_304,
        ),
        "pbpstats_po": (
            "e561465e5fc0c0513c2bf2692d351b27662ee9342c0fd9bf5da7beda38444b73",
            976_520,
        ),
    },
    2024: {
        "nbastats": ("8f370da00ad0a6d4157921bd161d56ea32647a165d906516f2b36384a6a4989a", 8_583_784),
        "nbastats_po": (
            "19c243bfb63305f8a7e5922f37acb781d587c2768493850e5fe852c901b8ce72",
            581_156,
        ),
        "nbastatsv3": (
            "38fb8bfb43be8db3d47576600f32f25d89cc3cc05ebac77a51f4db42faf0b841",
            8_781_060,
        ),
        "nbastatsv3_po": (
            "9995c1d4b14eae69a75294d9e20559cf515d54ff8c2d3167aedda4b4de5d2cb0",
            599_168,
        ),
        "shotdetail": (
            "950100f9c84fe750ae2ac8eaeb82d24cdfb9f60a9ed04ceaa66f64789d7c216e",
            2_832_144,
        ),
        "shotdetail_po": (
            "2a972625db433504486d837c38c917146da269939e6d984b8024f148d3d79507",
            191_548,
        ),
        "cdnnba": ("35a82e6b29821adb22b8474dea8c51e08847d8e00690d1d5ffde7d000e0087d1", 18_886_652),
        "cdnnba_po": (
            "065798b27908f9e16d8f9b6f19f429d0a798d98ce67aad116c9c9b7786f801f7",
            1_255_524,
        ),
        "datanba": ("79f698e66439e3e43bdb6299eb4da7897b5e007985193350da280c8a4ec76e60", 11_344_636),
        "datanba_po": ("62068c9b16aa789e90d395ecc7891ad853f1566968ebc280f9d5f3d39f22b855", 760_372),
        "pbpstats": (
            "3e124793cc7fbc279627926e207b634fd593e5b56a69b8d0324f21460913c5c6",
            13_739_644,
        ),
        "pbpstats_po": (
            "c41f2ae7e577d117694b47da67ad0b963a554eb0640e9fa7690c16781c4b20a2",
            433_808,
        ),
    },
}

# Bill Mill team and player box logs as (sha256, bytes), from the issue #51 register.
_BOX_PINS: dict[int, tuple[tuple[str, int], tuple[str, int]]] = {
    2017: (
        ("09ce5a1c9ba0db8c3dcd9a79df1dd070726fcb3f8a4a1951cef4b9df3568ee88", 158_915),
        ("c85d95c9516468aba14d4afb7de9ba693754d3fb407a529a89ca0ee35af48611", 1_618_976),
    ),
    2018: (
        ("e8e744d71159206a88be82bec62eeeefe54bd8083b8871158af643d1c9c17076", 159_551),
        ("c47e47e027c63271cb5e52d85bb7b5855ab338bc176b71a0327f9870d3d0b844", 1_634_095),
    ),
    2019: (
        ("3bccb3f6d1381d64498172e81afb796815b072b8edfc357fc602a8ef4e9bcf53", 149_363),
        ("33b2b4be41b9f26a3e249f572d936a341f2a2165e83461267b1a635e552e7200", 1_492_805),
    ),
    2020: (
        ("7d5289ca4eb37a692980e1b69d91a967d85546d6203a3a1721311bde596e7713", 142_782),
        ("e162c06ebf9d1bf19c6cef955142f24213e602c632823f045a39958e76eb95b4", 1_458_632),
    ),
    2021: (
        ("ebfe309962d4d6c31550b25f4d2816d341946f8c2d6e58246faad237ba63f99c", 158_877),
        ("6cea151853bbd901b84ddff93100eb571c6f8ca73d7124bcf0d127d6a06deb0e", 1_622_132),
    ),
    2022: (
        ("bd3b4a9f745249c970970beffd27813ce2ed7e235a9df20228fde042535a6c43", 157_942),
        ("5f378f06b35f36bf2aa928d2fb77c4d14ed87a4f43161f43b4e4de30c601638e", 1_608_541),
    ),
    2023: (
        ("25abfb7b0d94034193c7d848515ff8b70346e7fe07cf26694ca4936bc4b332c6", 160_365),
        ("73ad4a13099b63e3ba4d3bc3d8b2da0b400aea556b265af5004fc1a17452e851", 1_637_665),
    ),
    2024: (
        ("eb3d357ecf0914211c3d62bfd56a020fd61c4853efa925949a4ad9cf0b570397", 161_071),
        ("e974d0e94025b1bbb00af90441f943938230122304c9677c850dc134cff1d3bb", 1_651_318),
    ),
}

# Bentes regular-season and playoff lineup stints as (sha256, bytes, release asset ID).
_BENTES_PINS: dict[int, tuple[tuple[str, int, int], tuple[str, int, int]]] = {
    2017: (
        ("9e86aca93b3af2345049b5c1df76ddc60c635c30410388e067f5b067ffce9419", 1_298_311, 582066969),
        ("9bd46cc3c3c0c12111c6ab264bea931e280008f159354d0484936656f7523518", 91_657, 582065797),
    ),
    2018: (
        ("f739e1beba3fe933b73df74ccbe8a5170b0a927b24a4dff8822b81e5d6a5823d", 1_365_413, 603728050),
        ("466d05efda5536967da731ba56738f4bb6aead16dad23c9df7de94ee384079b8", 92_601, 582065824),
    ),
    2019: (
        ("38261e88040d3a8c59a2a26f6266a308b3d7dad5a65f1a7391c2d0bff10960f4", 1_211_140, 582067054),
        ("4e02b058da12f769376924665746d00be73b4c8329d11a11098cb3ed76ad9348", 94_640, 582065880),
    ),
    2020: (
        ("5c2a8a42a701b796d0b4be36e7ba33bdeb1f8a1044246cf3895f43142347471f", 1_204_965, 582067089),
        ("6200ee8c101b7744b69095c571ecfe2f07975ac7344ab315fa13838c045c327a", 92_018, 582065940),
    ),
    2021: (
        ("48d4919b1e9ed5c7de302251a64a9d5f4c79e7f2f81b4f78b24bedaaaf75ddd9", 1_478_458, 582067121),
        ("82def41b5cb5e29b279b2e9f56a8482fd6b20ddffec1b3b6c36995e2e6c9407d", 96_301, 582066006),
    ),
    2022: (
        ("e99075847d7748db1ea414b888fc00cfb9ee7bb9727e58794ef2e7fccbe2efb7", 1_469_829, 582067188),
        ("441759669ae9f7afbf39f4e40dc82dc4fe2378148d3e7036ad3f10b89d390260", 88_694, 582066033),
    ),
    2023: (
        ("325b2d18cdf09a0ba73bf51d32b62797bdb996bf82637c768b644d91d59c6420", 1_409_831, 582067239),
        ("60223eff0c8e587efcdd7b8951f641c86965360627254feaccf04d745210a5ec", 89_353, 582066062),
    ),
    2024: (
        ("3d4d1eaa57bb4585b7a9aaba2e77e0ad665d13d9e0b4b97d0859864f2d2b19b5", 1_497_184, 582067329),
        ("6e090b868c8bd049e52631b08facd1fc46dcefb98a8dc2c779c68926d7dfcb60", 94_824, 582066103),
    ),
}

SEASONS = tuple(sorted(_ARCHIVE_PINS))


def pinned_season(start_year: int) -> int:
    """Return a season with pinned sources, refusing the confirmatory holdout and later."""
    if start_year >= HOLDOUT_START_YEAR:
        raise ValueError(
            f"Season {start_year} is reserved for the confirmatory holdout (issue #42) "
            "and cannot be captured, loaded or built here"
        )
    if start_year not in _ARCHIVE_PINS:
        raise ValueError(f"No pinned sources for the season starting in {start_year}")
    return start_year


def _archive(name: str, sha256: str, size_bytes: int) -> Source:
    return Source(
        name,
        f"{ARCHIVE_BASE}/{name}",
        sha256,
        size_bytes,
        "shufinskiy",
        ARCHIVE_REVISION,
    )


def has_livedata(start_year: int) -> bool:
    """Whether the pinned archive holds NBA liveData (``cdnnba``) for this season.

    The #51 register records liveData as absent from the provider inventory before 2020–21.
    Builds for those seasons run without it, and every other feed is required.
    """
    return LIVEDATA in _ARCHIVE_PINS[pinned_season(start_year)]


def _archives(start_year: int, feeds: tuple[str, ...]) -> list[Source]:
    pins = _ARCHIVE_PINS[pinned_season(start_year)]
    return [
        _archive(f"{stem}_{start_year}.tar.xz", *pins[stem])
        for feed in feeds
        if feed != LIVEDATA or has_livedata(start_year)
        for stem in (feed, f"{feed}_po")
    ]


def lineup_stat_names(start_year: int) -> tuple[str, str]:
    """Bentes regular-season and playoff lineup files, which are named by ending year."""
    end = pinned_season(start_year) + 1
    return f"lineup_stats_regular_{end}.parquet", f"lineup_stats_playoffs_{end}.parquet"


def season_sources(start_year: int) -> tuple[Source, ...]:
    """Pinned build inputs for one season. Box logs keep season-neutral snapshot names."""
    team, player = _BOX_PINS[pinned_season(start_year)]
    end = start_year + 1
    return (
        *_archives(start_year, ("nbastats", "nbastatsv3", "shotdetail", "cdnnba", "datanba")),
        *(
            Source(
                f"{kind}_game_logs.parquet",
                f"{BOX_BASE}/{kind}_game_logs/season={end}/data.parquet",
                sha256,
                size_bytes,
                "billmill",
                local_name=f"{kind}_game_logs_{end}.parquet",
            )
            for kind, (sha256, size_bytes) in (("team", team), ("player", player))
        ),
    )


def season_evidence_sources(start_year: int) -> tuple[Source, ...]:
    """Pinned comparison feeds for one season. These files are never inputs to a build."""
    names = lineup_stat_names(start_year)
    return (
        *_archives(start_year, ("datanba", "cdnnba", "pbpstats")),
        *(
            Source(
                name,
                f"{BENTES_BASE}/lineup_stats/{name}",
                sha256,
                size_bytes,
                "bentes",
                f"github-release-asset-{asset}",
            )
            for name, (sha256, size_bytes, asset) in zip(
                names, _BENTES_PINS[start_year], strict=True
            )
        ),
    )


SOURCES = season_sources(2022)
# Independent comparison evidence. These files are never inputs to a pilot build.
EVIDENCE_SOURCES = season_evidence_sources(2022)


class Artifact(TypedDict):
    artifact_id: str
    name: str
    uri: str
    source_id: str
    upstream_namespace: str
    source_revision: str | None
    sha256: str
    size_bytes: int
    retrieved_at: str
    rights_ref: str


class Snapshot(TypedDict):
    schema_version: int
    season_start_year: int
    attribution: str
    terms: str
    artifacts: list[Artifact]
    # Set when the bytes were copied from a local audit capture instead of downloaded.
    # Each artifact's retrieved_at is then the modification time of the captured file.
    local_capture: NotRequired[str]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    with path.open("rb") as data:
        return file_digest(data, "sha256").hexdigest()


def verify_artifact(path: Path, source: Source) -> None:
    if path.stat().st_size != source.size_bytes or sha256_file(path) != source.sha256:
        raise ValueError(f"Source bytes differ from the audited snapshot for {source.name}")


def _download(path: Path, source: Source) -> str:
    with urlopen(source.uri, timeout=45) as response:
        with path.open("xb") as target:
            for block in iter(lambda: response.read(65536), b""):
                if target.tell() + len(block) > source.size_bytes:
                    raise ValueError(f"Source exceeds audited size for {source.name}")
                target.write(block)
    return utc_now()


def _copy_local(path: Path, source: Source, local: Path) -> str:
    original = local / (source.local_name or source.name)
    if not original.is_file():
        raise FileNotFoundError(f"Local capture lacks {original.name}")
    verify_artifact(original, source)
    with original.open("rb") as data, path.open("xb") as target:
        shutil.copyfileobj(data, target)
    modified = datetime.fromtimestamp(original.stat().st_mtime, timezone.utc)
    return modified.isoformat()


def capture_snapshot(
    directory: Path,
    sources: tuple[Source, ...] | None = None,
    season_start_year: int = 2022,
    local: Path | None = None,
) -> Snapshot:
    """Store one complete acquisition in a new, private directory.

    With ``local``, copy already captured bytes from that directory instead of downloading.
    Every file must match its pinned size and SHA-256 either way.
    """
    pinned_season(season_start_year)
    sources = season_sources(season_start_year) if sources is None else sources
    directory.mkdir(mode=0o700, parents=True)
    snapshot: Snapshot = {
        "schema_version": 1,
        "season_start_year": season_start_year,
        "attribution": ATTRIBUTION,
        "terms": NBA_TERMS,
        "artifacts": [],
    }
    if local is not None:
        snapshot["local_capture"] = "/".join(local.resolve().parts[-2:])
    try:
        for source in sources:
            path = directory / source.name
            if local is None:
                retrieved_at = _download(path, source)
            else:
                retrieved_at = _copy_local(path, source, local)
            verify_artifact(path, source)
            snapshot["artifacts"].append(
                Artifact(
                    artifact_id=f"{source.name}@{source.sha256}",
                    name=source.name,
                    uri=source.uri,
                    source_id=source.publisher,
                    upstream_namespace="nba",
                    source_revision=source.revision,
                    sha256=source.sha256,
                    size_bytes=source.size_bytes,
                    retrieved_at=retrieved_at,
                    rights_ref=RIGHTS_REF,
                )
            )
        write_json(directory / "snapshot.json", snapshot)
    except BaseException:
        shutil.rmtree(directory)
        raise
    return snapshot


def load_snapshot(
    directory: Path,
    sources: tuple[Source, ...] | None = None,
    season_start_year: int | None = None,
) -> Snapshot:
    snapshot = cast(Snapshot, json.loads((directory / "snapshot.json").read_text(encoding="utf-8")))
    year = snapshot["season_start_year"]
    if (
        snapshot["schema_version"] != 1
        or type(year) is not int
        or (season_start_year is not None and year != season_start_year)
        or snapshot["attribution"] != ATTRIBUTION
        or snapshot["terms"] != NBA_TERMS
    ):
        raise ValueError("Invalid source snapshot")
    pinned_season(year)
    sources = season_sources(year) if sources is None else sources
    records = {row["name"]: row for row in snapshot["artifacts"]}
    if len(records) != len(snapshot["artifacts"]) or records.keys() != {s.name for s in sources}:
        raise ValueError("Snapshot must contain each pinned artifact exactly once")
    for source in sources:
        record = records[source.name]
        if (
            record["uri"] != source.uri
            or record["sha256"] != source.sha256
            or record["size_bytes"] != source.size_bytes
            or record["artifact_id"] != f"{source.name}@{source.sha256}"
            or record["source_id"] != source.publisher
            or record["upstream_namespace"] != "nba"
            or record["source_revision"] != source.revision
            or record["rights_ref"] != RIGHTS_REF
        ):
            raise ValueError(f"Source manifest differs from the pinned record for {source.name}")
        captured = datetime.fromisoformat(record["retrieved_at"])
        if captured.tzinfo is None or captured.utcoffset() != timezone.utc.utcoffset(captured):
            raise ValueError(f"Source capture timestamp must be UTC for {source.name}")
        verify_artifact(directory / source.name, source)
    return snapshot
