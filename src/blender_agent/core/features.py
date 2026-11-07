"""VLM 参考图特征提取：把参考图变成 builder 可消费的参数。

流程：参考图 + 结构化提示词 -> LLM 返回 JSON -> 容错解析为 CatFeatures。
任何一步失败都回退默认值，绝不让主任务崩掉。
"""

import base64
import json
import re
from dataclasses import dataclass, replace

from blender_agent.core.types import ChatMessage

_PROMPT = (
    "仔细观察这张图片中的猫形角色，提取以下特征，只输出一个 JSON 对象，不要任何其他文字：\n"
    '{"fur": "主体毛色 hex，如 #e07820",\n'
    ' "muzzle": "吻部/口鼻/腹部浅色 hex，无浅色区则与 fur 相同",\n'
    ' "inner_ear": "耳内侧颜色 hex（多为粉/深色）",\n'
    ' "nose": "鼻子颜色 hex",\n'
    ' "iris": "虹膜颜色 hex",\n'
    ' "collar": "项圈/服饰颜色 hex，没有项圈就给 #ff5577",\n'
    ' "stripes": 毛色有明显条纹/斑纹填 true，纯色填 false,\n'
    ' "collar_on": 图中角色戴项圈/服饰填 true 否则 false,\n'
    ' "bow": 图中有蝴蝶结填 true 否则 false,\n'
    ' "whiskers": 能看到明显胡须填 true 否则 false}\n'
    "只依据图片实际内容填，不要脑补。"
)

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass
class CatFeatures:
    fur: str
    muzzle: str
    inner_ear: str
    nose: str
    iris: str
    collar: str
    stripes: bool
    collar_on: bool
    bow: bool
    whiskers: bool

    @classmethod
    def DEFAULTS(cls) -> "CatFeatures":
        # 默认值 = 现有 builder 的硬编码色，保证无图时行为与旧版完全一致
        return cls(fur="#eb8029", muzzle="#ebdecc", inner_ear="#f28d9e",
                   nose="#f28d9e", iris="#8c4d10", collar="#e68fa0",
                   stripes=True, collar_on=True, bow=True, whiskers=True)

    @classmethod
    def from_json(cls, text: str) -> "CatFeatures":
        d = _parse_json_object(text)
        if not isinstance(d, dict):
            return cls.DEFAULTS()
        base = cls.DEFAULTS()
        vals = {}
        for k in ("fur", "muzzle", "inner_ear", "nose", "iris", "collar"):
            v = d.get(k)
            if isinstance(v, str) and HEX_RE.match(v.strip()):
                vals[k] = v.strip().lower()
        flags = {}
        for k in ("stripes", "collar_on", "bow", "whiskers"):
            if isinstance(d.get(k), bool):
                flags[k] = d[k]
        return replace(base, **vals, **flags)

    def to_params(self) -> dict:
        return {"fur": self.fur, "muzzle": self.muzzle, "inner_ear": self.inner_ear,
                "nose": self.nose, "iris": self.iris, "collar": self.collar,
                "stripes": self.stripes, "collar_on": self.collar_on,
                "bow": self.bow, "whiskers": self.whiskers}


def _parse_json_object(text: str):
    if not text:
        return None
    s = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if m:
        s = m.group(1).strip()
    try:
        return json.loads(s)
    except Exception:  # noqa: 模型偶尔在 JSON 外加说明文字，取首个 {...} 块再试
        m = re.search(r"\{.*\}", s, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def extract_features(llm, image: bytes) -> CatFeatures:
    """把参考图交给多模态 LLM 提取特征；任何失败回退默认值。"""
    try:
        msg = ChatMessage(role="user", content=_PROMPT, images=[image])
        reply = llm.chat([msg])
        return CatFeatures.from_json(reply.content or "")
    except Exception:  # noqa: LLM 挂了也要能继续跑，用默认特征
        return CatFeatures.DEFAULTS()
