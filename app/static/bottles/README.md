# Downloaded bottle photographs

Empty until you run:

```bash
python scripts/fetch_images.py
```

That downloads the photographs listed in `data/champagnes.json` into this directory, and
`app/main.py` starts serving them instead of hotlinking the retailers — automatically,
by filename: `{slug}.jpg`. Commit what lands here.

Do it from a machine that can reach `champagne-terroir.fr`, `hachette-vins.shop` and
`ed-champ.fr`.

**Downloading is not permission.** These photographs belong to the retailer or the
producer. Ask each grower for written permission before publishing, or photograph the
bottles yourself on the buying trip — you will have them, and then you own the images
outright.
