#!/bin/bash

# Install dependencies required for Notebooks PDF exports

set -Eeuxo pipefail

# Mapping of `uname -m` values to equivalent GOARCH values
declare -A UNAME_TO_GOARCH
UNAME_TO_GOARCH["x86_64"]="amd64"
UNAME_TO_GOARCH["aarch64"]="arm64"
UNAME_TO_GOARCH["ppc64le"]="ppc64le"
UNAME_TO_GOARCH["s390x"]="s390x"

ARCH="${UNAME_TO_GOARCH[$(uname -m)]}"
if [[ -z "${ARCH:-}" ]]; then
    echo "Unsupported architecture: $(uname -m)" >&2
    exit 1
fi

# Skip PDF export installation for s390x and ppc64le architectures
if [[ "$(uname -m)" == "s390x" || "$(uname -m)" == "ppc64le" ]]; then
    echo "PDF export functionality is not supported on $(uname -m) architecture. Skipping installation."
    exit 0
fi

# https://github.com/rh-aiservices-bu/workbench-images/blob/main/snippets/ides/1-jupyter/os/os-packages.txt
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
# available in epel but not in rhel9
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
# https://bugzilla.redhat.com/show_bug.cgi?id=2284201
#texlive-listingsutf8
#texlive-pdfcol
#texlive-tikzfill
)

dnf install -y "${PACKAGES[@]}"
dnf clean all

pdflatex --version

# install texlive-tcolorbox by other means

# /usr/share/texlive/texmf-local/
TEXMFLOCAL=$(kpsewhich -var-value TEXMFLOCAL)

# https://tex.stackexchange.com/questions/24636/where-can-i-find-which-packages-are-available-as-tds-zip
# https://www.ctan.org/tex-archive/install/macros/latex/contrib
wget --progress=dot:giga -O /tmp/tcolorbox.zip https://mirrors.ctan.org/install/macros/latex/contrib/tcolorbox.tds.zip
unzip -q -o -d "${TEXMFLOCAL}" /tmp/tcolorbox.zip
rm /tmp/tcolorbox.zip
texhash "${TEXMFLOCAL}"

kpsewhich tcolorbox.sty

# pandoc installation
# https://github.com/jgm/pandoc/releases/3.7.0.2
curl -fL "https://github.com/jgm/pandoc/releases/download/3.7.0.2/pandoc-3.7.0.2-linux-${ARCH}.tar.gz"  -o /tmp/pandoc.tar.gz
mkdir -p /usr/local/pandoc
tar xvzf /tmp/pandoc.tar.gz --strip-components 1 -C /usr/local/pandoc/
rm -f /tmp/pandoc.tar.gz

# clean up /tmp
rm -rf /tmp/* /tmp/.[!.]*
