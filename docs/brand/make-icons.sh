#!/bin/sh
# Rebuilds the install icons in public/ from the two SVGs beside this script.
#
# The mark is म — the same letter that stands in for Masterji on every message
# in the chat log, so the icon on a home screen is the face already in the
# room. Marigold #e8a13c on chalkboard #10151a, which is --accent and --bg in
# app/globals.css.
#
# Why the PNGs are committed rather than generated at build time: the glyph is
# Devanagari and nothing in this repo ships a font that covers it (the fonts in
# app/layout.tsx are latin-only, deliberately). Rasterising here bakes the
# outline into the file, so the icon does not depend on the machine that serves
# it — or on the one that renders it. An SVG icon would show a box on anything
# without a Devanagari face.
#
# Why qlmanage: it is macOS's own Quick Look renderer and it is already on the
# machine. Adding sharp or resvg to package.json for four files that change
# roughly never is a dependency the deploy would carry forever.
#
# Two icons, not one: the "any" pair fills its square, and the maskable copy
# holds the same mark smaller so an Android launcher can crop it to a circle or
# a squircle without taking a bite out of the letter.
#
# Run from the repo root:  sh docs/brand/make-icons.sh
set -e

out=$(mktemp -d)
gen() { # svg, size, destination
  qlmanage -t -s "$2" -o "$out" "$1" >/dev/null 2>&1
  sips -z "$2" "$2" "$out/$(basename "$1").png" --out "$3" >/dev/null
  rm -f "$out/$(basename "$1").png"
}

gen docs/brand/icon.svg 512 public/icon-512.png
gen docs/brand/icon.svg 192 public/icon-192.png
gen docs/brand/icon.svg 180 public/apple-icon-180.png
gen docs/brand/icon-maskable.svg 512 public/icon-maskable-512.png

rm -rf "$out"
echo "wrote public/icon-{192,512}.png public/icon-maskable-512.png public/apple-icon-180.png"
