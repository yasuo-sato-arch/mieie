# Mieie (見える図面, "Visible Drawings")

**See where your architectural drawings went after you shared them — with a record nobody can rewrite.**

Built by Yasuo Sato, a licensed first-class architect (40 years of practice) in Fuchu, Tokyo, Japan.

## The problem

For every cost estimate, house drawings are copied to a builder and then to many subcontractors (carpenters, joiners, electricians). The drawings carry the client's **address, name and floor plan**. After sharing, nobody knows:

1. **where** the drawing went,
2. whether it was **deleted** (losing bidders keep them forever),
3. whether it was **altered**.

## What Mieie does

| Question | Answer | Component |
|---|---|---|
| Where did it go? | One link per recipient. Every opening is logged (time, device). | `distribution-tool/` |
| Was it deleted? | The file is never handed over — it is only *shown*. Revoke the link and it can no longer be opened. | `distribution-tool/` |
| Was it altered? | The SHA-256 fingerprint of the record is stamped on-chain. One extra line → mismatch. | `record-stamping-tool/` |

**Recipients need no wallet and no crypto knowledge** — they just open a link. Only the architect's office signs records.

## Components

### `record-stamping-tool/`
- `mieie_nft_tool.html` — single-file web app (ethers.js v6 + MetaMask). Tab 2 stamps a file's SHA-256 as a record; tab 3 verifies any PDF against the on-chain record.
- `MaintenanceRecordNFT.sol` — soulbound (non-transferable) ERC-721-style record ledger. Only the registrar (the office) can mint. Stores fingerprint + timestamp only; **no drawings, names or IPs on-chain**.
- Deployed on **Polygon Amoy testnet**: `0xa2F8674e91c4517A27f5E3d3Ff7266f085E5Db87`. Record #1 = a real survey report (Sep 14, 2026). EVM-compatible, so it can be redeployed to Ethereum L2s (e.g. Base, Arbitrum) without changes.
- Run: serve the folder over http (MetaMask does not work on `file://`), e.g. `python3 -m http.server 8000`.

### `distribution-tool/`
- `mieie_haifu.py` — Python standard library only (http.server + SQLite). Upload a PDF, issue per-recipient links (`/v/TOKEN`), PDF.js viewer with a recipient-name watermark, admin page with open counts and a revoke button.
- Daily log export is split into a **stamping copy** (random recipient ID, timestamp, document hash, salt — no names, IPs or user agents) and a private full copy. The stamping copy's fingerprint goes on-chain, so the day's access log can be proven unaltered.
- Run: `python3 mieie_haifu.py` (port 8787). `config.json` (admin key) and `data/` are created locally and must never be committed (see `.gitignore`).

## Status (honest)

- Prototype, testnet only. Tested end-to-end over the internet on Sep 26, 2026 — **with my own second device**. No third-party users yet.
- Known gap: a skilled user can still save the raw PDF. Next: serve watermarked page images only.
- Feedback from the University of Tokyo Blockchain Innovation entrepreneur program (Oct 3, 2026): lead with the business value of tracking; keep the chain to where it is necessary; target upstream builders and real-estate firms.

## Disclosure of prior work

The stamping tool and contract were first prototyped on Jul 17, 2026 (before the hackathon). During the hackathon window (Sep 14 – Oct 12, 2026): record ledger deployment and first real record, verification flow, the whole distribution tool, privacy-preserving log export, and explanatory videos.

Built with AI assistance (Claude) — the architect designs and decides; the AI writes the code.

## License

All rights reserved (prototype shared for hackathon review).
