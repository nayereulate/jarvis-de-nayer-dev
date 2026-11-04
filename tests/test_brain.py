import pytest

from jarvis import brain as brain_module
from jarvis import tools
from jarvis.brain import Brain


@pytest.fixture(autouse=True)
def temp_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(brain_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(brain_module, "AUDIT_LOG", tmp_path / "audit.log")


def scripted(*replies):
    queue = list(replies)
    prompts = []

    def llm(prompt, session_id):
        prompts.append(prompt)
        return {"session_id": "s1", **queue.pop(0)}

    llm.prompts = prompts
    return llm


def test_sensitive_action_waits_for_approval(monkeypatch):
    calls = []
    monkeypatch.setitem(tools.ALL_TOOLS, "restart_pc", lambda: calls.append("restart") or "ok")
    llm = scripted(
        {"say": "¿Reinicio?", "actions": [{"tool": "restart_pc", "args": {}}]},
        {"say": "Listo", "actions": []},
    )
    brain = Brain(llm=llm)

    reply = brain.chat("reinicia")
    assert calls == []
    assert reply["pending"]["actions"][0]["tool"] == "restart_pc"

    final = brain.resolve(reply["pending"]["id"], approved=True)
    assert calls == ["restart"]
    assert final["say"] == "Listo"


@pytest.mark.parametrize("tool, args", [
    ("run_powershell", {"command": "dir"}),
    ("kill_process", {"name": "notepad.exe"}),
])
def test_other_actions_run_without_asking(tool, args):
    assert not tools.needs_confirmation(tool, args)


@pytest.mark.parametrize("command", [
    "shutdown /s /t 0",
    "SHUTDOWN.exe /r",
    "Stop-Computer -Force",
    "Restart-Computer",
    "rundll32 powrprof.dll,SetSuspendState",
])
def test_power_commands_in_powershell_still_ask(command):
    assert tools.needs_confirmation("run_powershell", {"command": command})


@pytest.mark.parametrize("command", [
    "Remove-Item C:\\x.txt",
    "Get-ChildItem *.log | Remove-Item -Force",
    "rm x.txt",
    "del x.txt",
    "cmd /c DEL /q x.txt",
    "erase x.txt",
    "ri x.txt",
    "rd /s /q carpeta",
    "rmdir carpeta",
    "[IO.File]::Delete('x.txt')",
    "(Get-Item x.txt).Delete()",
    "Clear-RecycleBin -Force",
    "robocopy vacia destino /MIR",
])
def test_delete_commands_ask(command):
    assert tools.needs_confirmation("run_powershell", {"command": command})


@pytest.mark.parametrize("command", [
    "Get-ChildItem C:\\jarvis",
    "Get-Process | Sort-Object CPU",
    "Start-Process 'com.epicgames.launcher://'",
    "Get-Content C:\\modelo\\delta.txt",
    "robocopy origen destino",
])
def test_ordinary_commands_do_not_ask(command):
    assert not tools.needs_confirmation("run_powershell", {"command": command})


def test_denied_action_never_runs(monkeypatch):
    calls = []
    monkeypatch.setitem(tools.ALL_TOOLS, "shutdown_pc", lambda: calls.append(1))
    llm = scripted(
        {"say": "¿Apago?", "actions": [{"tool": "shutdown_pc", "args": {}}]},
        {"say": "No apagué", "actions": []},
    )
    brain = Brain(llm=llm)

    reply = brain.chat("apaga")
    brain.resolve(reply["pending"]["id"], approved=False)
    assert calls == []
    assert "rechazó" in llm.prompts[-1]


def test_pending_id_is_single_use():
    llm = scripted(
        {"say": "¿Apago?", "actions": [{"tool": "shutdown_pc", "args": {}}]},
        {"say": "No", "actions": []},
    )
    brain = Brain(llm=llm)
    pending_id = brain.chat("apaga")["pending"]["id"]
    brain.resolve(pending_id, approved=False)
    with pytest.raises(KeyError):
        brain.resolve(pending_id, approved=True)


def test_safe_action_result_goes_back_to_model():
    llm = scripted(
        {"say": "", "actions": [{"tool": "system_status", "args": {}}]},
        {"say": "Todo bien", "actions": []},
    )
    assert Brain(llm=llm).chat("estado")["say"] == "Todo bien"
    assert "cpu_percent" in llm.prompts[-1]


def test_unknown_tool_requires_confirmation_and_fails():
    assert tools.needs_confirmation("borrar_todo")
    assert tools.execute("borrar_todo")["ok"] is False


@pytest.mark.parametrize("url", ["file:///C:/x", "javascript:alert(1)", "https://a.com/ b", "calc.exe"])
def test_open_url_rejects_non_web_targets(url):
    assert tools.execute("open_url", {"url": url})["ok"] is False


def test_open_app_rejects_unlisted_app():
    assert tools.execute("open_app", {"name": "cmd"})["ok"] is False
