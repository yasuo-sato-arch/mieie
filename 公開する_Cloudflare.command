#!/bin/bash
# Mieie 見える図面 配布ツール ― Cloudflare クイックトンネルで外部公開(ダブルクリック用)
# localhost.run(無料)は30分ほどで公開アドレスが変わるため、止めるまでアドレスが変わらないこちらを使う。
# 「起動する.command」を先に動かしてから、これを実行してください。
#
# 初回だけ、Cloudflare 公式の cloudflared を GitHub の公式リリースからこのフォルダにダウンロードします。
#   配布元: https://github.com/cloudflare/cloudflared/releases (Cloudflare公式ドキュメントからのリンク先)
cd "$(dirname "$0")" || exit 1

if [ ! -x ./cloudflared ]; then
  case "$(uname -m)" in
    arm64)  PKG="cloudflared-darwin-arm64.tgz" ;;
    x86_64) PKG="cloudflared-darwin-amd64.tgz" ;;
    *) echo "このMacの種類($(uname -m))に合うものが分かりません。Coworkに見せてください。"; read -p "Enterで閉じます"; exit 1 ;;
  esac
  echo "初回のみ:Cloudflare公式の $PKG をダウンロードします…"
  curl -fL -o "$PKG" "https://github.com/cloudflare/cloudflared/releases/latest/download/$PKG" || { echo "ダウンロードに失敗しました。"; read -p "Enterで閉じます"; exit 1; }
  tar xzf "$PKG" && rm -f "$PKG" && chmod +x cloudflared
  echo "準備できました。"
  echo
fi

echo "外部公開を開始します。"
echo "しばらくすると、下の方に  https://〜.trycloudflare.com  というアドレスが出ます。これが公開アドレスです。"
echo "このアドレスは、この窓を閉じる(Control + C)まで変わりません。"
echo
echo "管理画面は  https://〜.trycloudflare.com/admin/管理キー"
echo "(管理キーは「起動する」の窓の /admin/ の後ろ。最後の _off なども含めて全部)"
echo
./cloudflared tunnel --no-autoupdate --url http://localhost:8787
