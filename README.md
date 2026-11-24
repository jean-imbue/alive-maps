# alive maps~

Walking routes that favor greenery, views, and street life, within the extra time you have.
Pick a start and an end, choose how much of a detour you can take, and it finds a nicer way
there, listing the parks, views and places you pass.

Map data and place search come from OpenStreetMap (© OpenStreetMap contributors) and Photon.

## Run it

- **Cloud in a Bottle:** Deploy app, paste this repo's URL. `cloudinabottle.toml` makes every
  page public, so anyone with the link can use it.
- **Anywhere with Docker:** `docker build -t alive-maps . && docker run -p 8080:8080 alive-maps`
- **Locally:** `pip install -r requirements.txt && gunicorn --bind 127.0.0.1:8080 alive_maps.server:app`

Fonts: Ovo (SIL Open Font License, `alive_maps/assets/OVO-LICENSE.txt`).
Map library: Leaflet (BSD-2-Clause, `alive_maps/assets/LEAFLET-LICENSE.txt`).
