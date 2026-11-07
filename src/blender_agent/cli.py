import typer
from rich import print as rprint

from blender_agent.core.agent import Agent
from blender_agent.config import load_config

app = typer.Typer()


@app.command()
def run(goal: str, workspace: str = "./workspace",
        image: str = typer.Option(None, "--image", help="参考图路径，支持按图建模")):
    """运行 Agent 完成一个 3D 制作目标，可附参考图。"""
    cfg = load_config(); cfg.workspace = workspace
    agent = Agent.from_config(cfg)
    img = open(image, "rb").read() if image else None
    out = agent.run(goal, image=img)
    rprint(f"[green]完成[/] 步骤 {len(out['steps_log'])} 个，交付：{out['deliverables']}")


@app.command()
def check():
    """仅做场景自检。"""
    cfg = load_config()
    agent = Agent.from_config(cfg)
    rprint(agent._scene())


if __name__ == "__main__":
    app()
