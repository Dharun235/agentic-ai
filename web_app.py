"""Small FastAPI adapter for the named-run ROS2 agent."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from pipelines.ros_agent import cancel, resume_run, start_run
from pipelines.ros_agent.run_service import RunNotFound, RunRepository
from pipelines.ros_agent import telemetry


app = FastAPI(title="ROS2 Agent")
repository = RunRepository()


@app.get("/", response_class=HTMLResponse)
def index():
    page = """<!doctype html>
<html><head><meta charset="utf-8"><title>ROS2 Agent</title>
<style>body{font:16px system-ui;max-width:960px;margin:32px auto;padding:0 16px;background:#f6f7f9}textarea,input,button{font:inherit;padding:9px;margin:4px 0}input,textarea{width:100%;box-sizing:border-box}button{cursor:pointer}pre{white-space:pre-wrap;background:white;padding:14px;border-radius:8px}section{background:white;padding:18px;margin:14px 0;border-radius:10px}#terminal{color:#175d2a}.muted{color:#666}</style>
</head><body><h1>ROS2 Agent</h1>
<p class="muted">One named task per session. Phoenix: <a href="__PHOENIX_UI__" target="_blank">open observability</a> (<a href="/observability" target="_blank">status</a>)</p>
<section id="start"><label>Session name</label><input id="name" placeholder="nodes-check"><label>Task</label><textarea id="task" rows="3" placeholder="List ROS2 nodes and topics"></textarea><button onclick="start()">Create plan</button></section>
<section><h2 id="state">No active session</h2><pre id="plan"></pre><button id="approve" onclick="approve()" disabled>Approve and execute</button><button id="revise" onclick="revise()" disabled>Revise plan</button><button id="stop" onclick="stopRun()" disabled>Stop</button><button id="new" onclick="newSession()" hidden>New session</button></section>
<section><h2>Live events</h2><pre id="events"></pre></section><section><h2>Output</h2><pre id="output"></pre><p id="saved"></p></section>
<script>
let run=null, timer=null;
const $=id=>document.getElementById(id);
function show(s){$('state').textContent=s.status+(s.run_name?' — '+s.run_name:'');$('plan').textContent=s.plan?JSON.stringify(s.plan,null,2):'';if(s.answer||s.error)$('output').textContent=s.answer||s.error;}
async function start(){const name=$('name').value.trim(),task=$('task').value.trim();if(!name||!task)return alert('Session name and task required.');const r=await fetch('/runs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({name,task})});const s=await r.json();if(!r.ok)return alert(s.detail||'Could not create run');run=name;show(s);$('approve').disabled=s.status!=='awaiting_approval';$('revise').disabled=s.status!=='awaiting_approval';$('stop').disabled=false;poll();}
async function approve(){const s=await action('approve','POST');if(s)show(s);}
async function revise(){const feedback=prompt('What should change?');if(!feedback)return;const s=await action('revise','POST',{feedback});if(s)show(s);}
async function stopRun(){if(run)await action('cancel','POST');}
async function action(path,method,body){const r=await fetch('/runs/'+encodeURIComponent(run)+'/'+path,{method,headers:{'content-type':'application/json'},body:body?JSON.stringify(body):undefined});const s=await r.json();if(!r.ok)return alert(s.detail||'Request failed');return s;}
async function poll(){if(!run)return;const [s,e]=await Promise.all([fetch('/runs/'+encodeURIComponent(run)).then(r=>r.json()),fetch('/runs/'+encodeURIComponent(run)+'/events').then(r=>r.json())]);show(s);$('events').textContent=JSON.stringify(e,null,2);$('approve').disabled=s.status!=='awaiting_approval';$('revise').disabled=s.status!=='awaiting_approval';$('stop').disabled=['complete','failed','cancelled'].includes(s.status);if(['complete','failed','cancelled','needs_input'].includes(s.status)){clearTimeout(timer);$('new').hidden=false;$('saved').textContent='Run artifacts: data/runs/'+run+'/';}else timer=setTimeout(poll,1000);}
function newSession(){location.reload();}
</script></body></html>"""
    return page.replace("__PHOENIX_UI__", telemetry.PHOENIX_UI)


@app.get("/observability")
def observability():
    return {**telemetry.status(), "open": telemetry.PHOENIX_UI}


class StartRequest(BaseModel):
    name: str = Field(min_length=1)
    task: str = Field(min_length=1)


class RevisionRequest(BaseModel):
    feedback: str = Field(min_length=1)


def _state_payload(state):
    return {
        "run_name": state.run_name,
        "status": state.status,
        "task": state.task,
        "answer": state.answer,
        "error": state.failure_reason,
        "plan": state.tasks,
        "observations": state.observations,
    }


@app.post("/runs")
def create_run(request: StartRequest):
    try:
        return _state_payload(start_run(request.task, request.name))
    except (ValueError, FileExistsError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/runs/{name}")
def get_run(name: str):
    try:
        return repository.status(name)
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/runs/{name}/plan")
def get_plan(name: str):
    try:
        return {"run_name": name, "status": repository.status(name)["status"], "tasks": repository.plan(name)}
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/runs/{name}/observations")
def get_observations(name: str):
    try:
        return {"run_name": name, "observations": repository.observations(name)}
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/runs/{name}/result")
def get_result(name: str):
    try:
        manifest = repository.manifest(name)
        return {
            "run_name": name,
            "status": manifest["status"],
            "answer": manifest.get("answer"),
            "error": manifest.get("error"),
            "observations": repository.observations(name),
        }
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/runs/{name}/approve")
def approve_run(name: str):
    try:
        return _state_payload(resume_run(name, approve=True))
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/runs/{name}/revise")
def revise_run(name: str, request: RevisionRequest):
    try:
        return _state_payload(resume_run(name, feedback=request.feedback))
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/runs/{name}/cancel")
def cancel_run(name: str):
    try:
        return {"run_name": name, "status": "cancellation_requested", "marker": str(cancel(name))}
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/runs/{name}/events")
def run_events(name: str):
    try:
        return repository.events(name)
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/runs/{name}/debug")
def run_debug(name: str):
    try:
        return repository.debug(name)
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/runs/{name}/observability")
def run_observability(name: str):
    try:
        events = repository.events(name)
        traces = [event for event in events if event.get("component") == "observability"]
        return {
            "run_name": name,
            "phoenix_url": telemetry.PHOENIX_UI,
            "project": telemetry.PHOENIX_PROJECT,
            "traces": traces,
        }
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
