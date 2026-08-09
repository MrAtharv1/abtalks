from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from app.db.database import get_db
from app.db.models import Agent, Post, Belief, AgentCycle
import json

router = APIRouter(tags=["dashboard"])

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>THREAD - Judge Dashboard</title>
    <style>
        body {{ font-family: -apple-system, system-ui, sans-serif; background: #f4f4f9; color: #333; margin: 0; padding: 20px; }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        .header {{ text-align: center; margin-bottom: 40px; }}
        .header h1 {{ margin: 0; font-size: 2.5em; color: #222; }}
        .header p {{ color: #666; font-size: 1.2em; }}
        
        .agent-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .agent-card h2 {{ margin-top: 0; }}
        .status-badge {{ display: inline-block; padding: 5px 10px; border-radius: 12px; font-size: 0.9em; font-weight: bold; background: #e0f2f1; color: #00796b; }}
        
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        .section {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); max-height: 600px; overflow-y: auto; }}
        
        .post, .belief {{ border-bottom: 1px solid #eee; padding-bottom: 15px; margin-bottom: 15px; }}
        .post:last-child, .belief:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
        
        .post-date, .belief-meta {{ font-size: 0.85em; color: #888; }}
        .post-text {{ font-size: 1.1em; line-height: 1.5; }}
        .rationale {{ background: #f9f9f9; padding: 10px; border-left: 3px solid #ccc; font-size: 0.9em; margin-top: 10px; }}
        
        .belief-statement {{ font-weight: bold; font-size: 1.05em; }}
        .confidence-bar {{ height: 8px; background: #eee; border-radius: 4px; overflow: hidden; margin-top: 5px; }}
        .confidence-fill {{ height: 100%; background: #4caf50; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>THREAD</h1>
            <p>Autonomous AI Creator Dashboard</p>
        </div>
        
        {content}
        
    </div>
</body>
</html>
"""

@router.get("/", response_class=HTMLResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    # Get the most recent active agent
    result = await db.execute(select(Agent).order_by(desc(Agent.created_at)).limit(1))
    agent = result.scalar_one_or_none()
    
    if not agent:
        return HTMLResponse(HTML_TEMPLATE.format(content="<div class='agent-card'><p>No active agents found. Please initialize an agent via API.</p></div>"))
        
    posts_res = await db.execute(select(Post).where(Post.agent_id == agent.id).order_by(desc(Post.created_at)).limit(20))
    posts = posts_res.scalars().all()
    
    beliefs_res = await db.execute(select(Belief).where(Belief.agent_id == agent.id).order_by(desc(Belief.last_revised_at)).limit(20))
    beliefs = beliefs_res.scalars().all()
    
    agent_html = f"""
    <div class="agent-card">
        <h2>Agent ID: {agent.id[:8]}...</h2>
        <p>System Status: <span class="status-badge">{agent.status}</span></p>
        <p>Runtime Status: <span class="status-badge" style="background:#fff3e0; color:#e65100;">{agent.runtime_status}</span></p>
    </div>
    """
    
    posts_html = ""
    for p in posts:
        try:
            rationale = json.loads(p.rationale) if p.rationale else {}
            why = rationale.get("why_selected", rationale.get("why_now", "No rationale recorded."))
        except:
            why = p.rationale
            
        posts_html += f"""
        <div class="post">
            <div class="post-date">{p.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</div>
            <div class="post-text">{p.text}</div>
            <div class="rationale"><strong>Rationale:</strong> {why}</div>
        </div>
        """
    if not posts_html:
        posts_html = "<p>No posts published yet. Waiting for editorial decisions...</p>"
        
    beliefs_html = ""
    for b in beliefs:
        conf_pct = int(b.confidence * 100)
        color = "#4caf50" if b.confidence >= 0.5 else "#f44336"
        beliefs_html += f"""
        <div class="belief">
            <div class="belief-meta">{b.status} | Confidence: {conf_pct}%</div>
            <div class="belief-statement">{b.statement}</div>
            <div class="confidence-bar"><div class="confidence-fill" style="width: {conf_pct}%; background: {color};"></div></div>
        </div>
        """
    if not beliefs_html:
        beliefs_html = "<p>No beliefs formed yet. Waiting for research evidence...</p>"
        
    grid_html = f"""
    <div class="grid">
        <div class="section">
            <h3>Publishing Feed</h3>
            {posts_html}
        </div>
        <div class="section">
            <h3>Internal Memory & Beliefs</h3>
            {beliefs_html}
        </div>
    </div>
    """
    
    return HTMLResponse(HTML_TEMPLATE.format(content=agent_html + grid_html))
