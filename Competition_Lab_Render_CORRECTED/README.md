# Competition Lab: fixed upload structure for Render

**Extract the ZIP.** In GitHub, upload `server.py`, `requirements.txt`, `render.yaml`, and the whole `public` folder directly to the repository root. Do **not** upload any enclosing folder.

Correct layout:
```
repository/
  server.py
  requirements.txt
  render.yaml
  public/
    index.html
    host.html
    common.js
    player.js
    host.js
    style.css
  tests/
```

On Render: Root Directory = blank. For a Web Service use build command `pip install -r requirements.txt` and start command `python server.py`; set environment variable `HOST_PIN` to your private facilitator password. For a Blueprint, use the root-level `render.yaml`.

After deployment: `https://your-render-domain/host`.

Do not run more than one instance: game state is stored in memory. Free hosting can sleep/restart, losing active game state.
