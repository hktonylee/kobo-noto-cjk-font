# Noto CJK Font

This package contains a pre-built CJK font [`NotoSerifCJK-Light.ttf`](NotoSerifCJK-Light.ttf). You can use this font to display the common Chinese, Japanese, and Korean characters with only one font file. This is particularly useful for Kobo e-readers.

Please report any missing characters to us ;-)

In addition, this package also contains a tool which can be used to produce the CJK font file that contains the common Chinese, Japanese, and Korean characters. You can use this tool to produce Sans Serif CJK font if you want.

# Font Installation

Download the pre-built CJK font [`NotoSerifCJK-Light.ttf`](NotoSerifCJK-Light.ttf) and install the font.

If you are using Kobo, you can follow this guide to install the font: https://help.kobo.com/hc/en-us/articles/13009477876631-Load-fonts-onto-your-Kobo-eReader

# Script Usage

You can install the requirements by running `pip install -r requirements.txt` first.

Then you can run the script to produce the CJK font file that contains the common Chinese, Japanese, and Korean characters.

This is an example of how to run the script:

```
python3 merge-cjk-font.py \
    --latin NotoSerif-Light.ttf \
    --zh-cn NotoSerifSC-Light.ttf \
    --zh-tw NotoSerifTC-Light.ttf \
    --add-latin1 \
    --add-cjk-punct \
    --add-jp-syllabaries \
    --add-halfwidth \
    --add-han-basic \
    --drop-tables vhea vmtx \
    --out NotoSerifCJK-Light.ttf
```
