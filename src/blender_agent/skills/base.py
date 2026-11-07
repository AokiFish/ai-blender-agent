from abc import ABC, abstractmethod

from blender_agent.core.types import Step


class Skill(ABC):
    name: str = ""

    @abstractmethod
    def build_steps(self, goal: str, ctx: dict) -> list[Step]: ...

    @abstractmethod
    def accept(self, goal: str) -> bool: ...   # 该 skill 是否匹配此目标
