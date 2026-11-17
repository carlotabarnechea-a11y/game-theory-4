COMPETITION LAB - CORRECTED GITHUB UPLOAD STRUCTURE

This ZIP opens directly with these items at the top level:
  server.py
  requirements.txt
  render.yaml
  public/ (contains index.html, host.html, and other website files)
  tests/

IMPORTANT: Extract the ZIP and upload THESE ITEMS to the TOP LEVEL of your GitHub repository.
Do not upload an extra enclosing folder named competition_lab.
Do not rename the public folder.

On GitHub, the first page of your repository must show server.py, requirements.txt,
render.yaml, and public side by side. The public folder must contain index.html
and host.html. If using a Render Web Service, Root Directory must be empty.
If using a Render Blueprint, create Blueprint based on the root render.yaml.

If there is an existing extra competition_lab folder in your GitHub repository,
it does not need to be used by Render once the root-level files are in place.

After a successful deploy, go to https://YOUR-RENDER-URL/host.
