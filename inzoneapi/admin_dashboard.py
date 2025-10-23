"""
AI Engagement Admin Dashboard

Simple HTML dashboard for monitoring and controlling AI engagement system
"""

def get_admin_dashboard_html():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>InZone AI Engagement Admin</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        .stat-card h3 {
            margin: 0 0 5px 0;
            font-size: 2em;
        }
        .stat-card p {
            margin: 0;
            opacity: 0.9;
        }
        button {
            background: #4CAF50;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            margin: 5px;
        }
        button:hover {
            background: #45a049;
        }
        button.danger {
            background: #f44336;
        }
        button.danger:hover {
            background: #da190b;
        }
        .config-section {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
        }
        .config-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            background-color: #f9f9f9;
            border-radius: 5px;
        }
        input[type="number"] {
            width: 80px;
            padding: 5px;
            border: 1px solid #ddd;
            border-radius: 3px;
        }
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status-running {
            background-color: #4CAF50;
        }
        .status-stopped {
            background-color: #f44336;
        }
        .log-container {
            max-height: 300px;
            overflow-y: auto;
            background-color: #f9f9f9;
            padding: 15px;
            border-radius: 5px;
            font-family: monospace;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 InZone AI Engagement Admin</h1>
        <p>Monitor and control AI character interactions</p>
    </div>

    <div class="stats-grid" id="statsGrid">
        <!-- Stats will be loaded here -->
    </div>

    <div class="card">
        <h2>🎛️ Scheduler Control</h2>
        <div id="schedulerStatus">
            <span class="status-indicator status-stopped"></span>
            Scheduler Status: <span id="statusText">Loading...</span>
        </div>
        <div style="margin-top: 15px;">
            <button onclick="controlScheduler('start')">▶️ Start Scheduler</button>
            <button onclick="controlScheduler('stop')" class="danger">⏹️ Stop Scheduler</button>
            <button onclick="triggerManualCycle()">🔄 Trigger Manual Cycle</button>
        </div>
    </div>

    <div class="card">
        <h2>⚙️ Configuration</h2>
        <div class="config-section" id="configSection">
            <!-- Config will be loaded here -->
        </div>
        <button onclick="saveConfig()" style="margin-top: 15px;">💾 Save Configuration</button>
    </div>

    <div class="card">
        <h2>📊 Analytics</h2>
        <div style="margin-bottom: 15px;">
            <button onclick="loadTrends(7)">📈 7 Day Trends</button>
            <button onclick="loadTrends(30)">📈 30 Day Trends</button>
            <button onclick="loadTopAIs()">🏆 Top Engaging AIs</button>
        </div>
        <div id="analyticsContainer">
            Click a button above to load analytics data.
        </div>
    </div>

    <div class="card">
        <h2>📝 Activity Log</h2>
        <div class="log-container" id="logContainer">
            Loading activity log...
        </div>
        <button onclick="refreshLogs()" style="margin-top: 10px;">🔄 Refresh Logs</button>
    </div>

    <script>
        let config = {};

        // Load initial data
        loadStats();
        loadSchedulerStatus();
        loadConfig();
        refreshLogs();

        // Refresh stats every 30 seconds
        setInterval(loadStats, 30000);
        setInterval(loadSchedulerStatus, 30000);

        async function loadStats() {
            try {
                const response = await fetch('/api/ai/engagement/stats');
                const data = await response.json();
                
                if (data.success) {
                    const stats = data.data;
                    document.getElementById('statsGrid').innerHTML = `
                        <div class="stat-card">
                            <h3>${stats.total_today}</h3>
                            <p>Total Interactions Today</p>
                        </div>
                        <div class="stat-card">
                            <h3>${stats.comments_today}</h3>
                            <p>Comments Today</p>
                        </div>
                        <div class="stat-card">
                            <h3>${stats.likes_today}</h3>
                            <p>Likes Today</p>
                        </div>
                        <div class="stat-card">
                            <h3>${stats.dms_today}</h3>
                            <p>DMs Today</p>
                        </div>
                        <div class="stat-card">
                            <h3>${stats.active_ai_users}</h3>
                            <p>Active AI Users</p>
                        </div>
                    `;
                }
            } catch (error) {
                console.error('Error loading stats:', error);
            }
        }

        async function loadSchedulerStatus() {
            try {
                const response = await fetch('/api/ai/engagement/scheduler/status');
                const data = await response.json();
                
                if (data.success) {
                    const status = data.data;
                    const statusText = document.getElementById('statusText');
                    const indicator = document.querySelector('.status-indicator');
                    
                    if (status.running) {
                        statusText.textContent = 'Running';
                        indicator.className = 'status-indicator status-running';
                    } else {
                        statusText.textContent = 'Stopped';
                        indicator.className = 'status-indicator status-stopped';
                    }
                }
            } catch (error) {
                console.error('Error loading scheduler status:', error);
            }
        }

        async function controlScheduler(action) {
            try {
                const response = await fetch('/api/ai/engagement/scheduler/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action })
                });
                
                const data = await response.json();
                alert(data.message || (data.success ? 'Success' : 'Error'));
                loadSchedulerStatus();
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }

        async function triggerManualCycle() {
            try {
                const response = await fetch('/api/ai/engagement/trigger', {
                    method: 'POST'
                });
                
                const data = await response.json();
                alert(data.message || (data.success ? 'Manual cycle triggered!' : 'Error'));
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }

        async function loadConfig() {
            try {
                const response = await fetch('/api/ai/engagement/config');
                const data = await response.json();
                
                if (data.success) {
                    config = data.data;
                    const configSection = document.getElementById('configSection');
                    configSection.innerHTML = `
                        <div class="config-item">
                            <label>Max Daily Interactions:</label>
                            <input type="number" id="max_daily_interactions" value="${config.max_daily_interactions}">
                        </div>
                        <div class="config-item">
                            <label>Comment Probability:</label>
                            <input type="number" step="0.1" id="comment_probability" value="${config.comment_probability}">
                        </div>
                        <div class="config-item">
                            <label>Like Probability:</label>
                            <input type="number" step="0.1" id="like_probability" value="${config.like_probability}">
                        </div>
                        <div class="config-item">
                            <label>DM Probability:</label>
                            <input type="number" step="0.1" id="dm_probability" value="${config.dm_probability}">
                        </div>
                    `;
                }
            } catch (error) {
                console.error('Error loading config:', error);
            }
        }

        async function saveConfig() {
            try {
                const newConfig = {
                    max_daily_interactions: parseInt(document.getElementById('max_daily_interactions').value),
                    comment_probability: parseFloat(document.getElementById('comment_probability').value),
                    like_probability: parseFloat(document.getElementById('like_probability').value),
                    dm_probability: parseFloat(document.getElementById('dm_probability').value)
                };

                const response = await fetch('/api/ai/engagement/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(newConfig)
                });
                
                const data = await response.json();
                alert(data.message || (data.success ? 'Configuration saved!' : 'Error saving config'));
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }

        async function loadTrends(days) {
            try {
                const response = await fetch(`/api/ai/engagement/analytics/trends?days=${days}`);
                const data = await response.json();
                
                if (data.success) {
                    const trends = data.data;
                    let html = `<h3>📈 Engagement Trends (${days} days)</h3><table border="1" style="width:100%; border-collapse: collapse;">
                                <tr><th>Date</th><th>Total</th><th>Comments</th><th>Likes</th><th>DMs</th><th>Active AIs</th></tr>`;
                    
                    for (const [date, stats] of Object.entries(trends)) {
                        html += `<tr>
                            <td>${date}</td>
                            <td>${stats.total}</td>
                            <td>${stats.comments}</td>
                            <td>${stats.likes}</td>
                            <td>${stats.dms}</td>
                            <td>${stats.ai_users_active}</td>
                        </tr>`;
                    }
                    html += '</table>';
                    
                    document.getElementById('analyticsContainer').innerHTML = html;
                }
            } catch (error) {
                console.error('Error loading trends:', error);
            }
        }

        async function loadTopAIs() {
            try {
                const response = await fetch('/api/ai/engagement/analytics/top-ais?days=7&limit=10');
                const data = await response.json();
                
                if (data.success) {
                    const topAIs = data.data;
                    let html = '<h3>🏆 Top Engaging AI Users (7 days)</h3><ol>';
                    
                    for (const [aiId, count] of topAIs) {
                        html += `<li><strong>${aiId}</strong>: ${count} interactions</li>`;
                    }
                    html += '</ol>';
                    
                    document.getElementById('analyticsContainer').innerHTML = html;
                }
            } catch (error) {
                console.error('Error loading top AIs:', error);
            }
        }

        async function refreshLogs() {
            // This is a placeholder - you might want to implement actual logging
            document.getElementById('logContainer').innerHTML = 
                `[${new Date().toLocaleString()}] Dashboard refreshed\\n` +
                `[${new Date().toLocaleString()}] Monitoring AI engagement system...\\n` +
                `[${new Date().toLocaleString()}] System operational`;
        }
    </script>
</body>
</html>
    """
