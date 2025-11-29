#!/bin/bash
set -Eeuxo pipefail

PACKAGES=(
texlive-adjustbox
texlive-bibtex
texlive-charter
texlive-ec
texlive-euro
texlive-eurosym
texlive-fpl
texlive-jknapltx
texlive-knuth-local
texlive-lm-math
texlive-marvosym
texlive-mathpazo
texlive-mflogo-font
texlive-parskip
texlive-plain
texlive-pxfonts
texlive-rsfs
# available in c9s but not in rhel9
#texlive-tcolorbox
texlive-times
texlive-titling
texlive-txfonts
texlive-ulem
texlive-upquote
texlive-utopia
texlive-wasy
texlive-wasy-type1
texlive-wasysym
texlive-xetex
)

dnf install -y "${PACKAGES[@]}"
dnf clean all

pdflatex --version
