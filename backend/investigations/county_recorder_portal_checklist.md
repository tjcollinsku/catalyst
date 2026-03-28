# Ohio County Recorder Portal Connectivity Checklist

**Purpose:** Track which county recorder portals are accessible without VPN (i.e., from a standard browser in incognito mode). Used to audit and correct `county_recorder_connector.py`.

**How to use:**
1. Open each URL in an **incognito/private browser window with VPN off**
2. Mark `✅ Works` if the page loads and search is functional
3. Mark `❌ Times Out` if the connection times out or the page fails to load
4. Mark `⚠️ Partial` if the page loads but search doesn't work (login wall, JS errors, etc.)
5. Mark `❓ Unverified` if not yet tested
6. Add notes in the Notes column for anything unusual (redirect, new URL, different system than expected, etc.)

**Last updated:** 2026-03-28

---

## ⚠️ Active Outage: GovOS CountyFusion Platform — 2026-03-28

**All CountyFusion servers are currently down.** Live browser testing on 2026-03-28 confirmed that `countyfusion2.govos.com`, `countyfusion4.govos.com`, and `countyfusion6.govos.com` all fail to load — the connection drops immediately with no response (not a timeout, an immediate connection failure). This is a **platform-wide GovOS outage**, not a VPN issue.

Confirmed failing URLs tested today:
- `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=SenecaOH` ❌
- `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=HighlandOH` ❌
- `https://countyfusion4.govos.com/` ❌
- `https://countyfusion2.govos.com/` ❌
- `https://countyfusion6.govos.com/` ❌

**Re-test CountyFusion counties when outage is resolved.** The connector URL entries for CountyFusion counties may still be correct — we just can't verify them until the platform is back.

This checklist also tracks counties that have **migrated away from CountyFusion** to other systems (like DTS PAXWorld) — the connector may have stale URLs for these regardless of the outage.

---

## System Key

| Code | System | Notes |
|------|--------|-------|
| `CF` | GovOS CountyFusion | `countyfusion4.govos.com` or `countyfusion12.govos.com` — **platform-wide outage as of 2026-03-28. URLs may still be correct — re-test when back online** |
| `CS` | GovOS Cloud Search | `publicsearch.us` — no login required, generally reliable |
| `DTS` | DTS PAXWorld | `dts-oh.com` or county-hosted — Document Technology Systems |
| `EW` | EagleWeb | County-hosted EagleWeb instance |
| `LAR` | Laredo (Fidlar) | Subscription required for most counties |
| `USL` | USLandRecords | `uslandrecords.com/ohlr3/` — free public access |
| `CUS` | Custom/Other | County-hosted custom system |
| `N/A` | In-Person Only | No online access |

---

## All 88 Counties

> **Legend:** ✅ Works · ❌ Times Out · ⚠️ Partial · ❓ Unverified

| # | County | System in Connector | Portal URL | Status | Notes |
|---|--------|---------------------|------------|--------|-------|
| 1 | Adams | **CUS** ✏️ | https://adamscountyoh.gov/recorder/ | ✅ | *Was DTS/CF* — Gemini verified: local custom portal, independent of all vendor outages |
| 2 | Allen | **DTS** ✏️ | https://recorderexternal.allencountyohio.com/paxworld/ | ✅ | *Was CF* — DTS PAXWorld. Gemini verified. |
| 3 | Ashland | CF ✏️ | https://countyfusion10.kofiletech.us/countyweb/loginDisplay.action?countyname=AshlandOH | ❌ | *URL corrected* — uses kofiletech.us domain (legacy CF). CF platform outage 2026-03-28. |
| 4 | Ashtabula | **COTT** ✏️ | https://cotthosting.com/ohashtabula/User/Login.aspx | ✅ | *Was CF* — Gemini verified: Cott Systems. Not affected by GovOS outage. |
| 5 | Athens | **AVA** ✏️ | https://ohathens.fidlar.com/OHAthens/AvaWeb/ | ✅ | *Was CF* — Gemini verified: migrated to Fidlar AVA. |
| 6 | Auglaize | **CUS** ✏️ | http://gis.auglaizecounty.org/scanneddrawings/ | ✅ | *Was CF* — Gemini verified: custom GIS/Scanned Drawings portal. |
| 7 | Belmont | **CUS** ✏️ | https://belmontcountyrecorder.org/ | ✅ | *Was CF* — Gemini verified: new custom site. |
| 8 | Brown | **CUS** ✏️ | https://www.browncountyohio.gov/index.php/recorder44 | ✅ | *Was CF* — Gemini verified: custom county portal. |
| 9 | Butler | **CS** ✏️ | https://butler.oh.publicsearch.us/ | ✅ | *Was CUS* — Gemini verified: GovOS Cloud Search. Working. |
| 10 | Carroll | CS | https://carroll.oh.publicsearch.us/ | ✅ | GovOS Cloud Search. Confirmed working (tested 2026-03-28). |
| 11 | Champaign | **AVA** ✏️ | https://ava.fidlar.com/OHChampaign/AvaWeb/ | ✅ | *Was CF* — Gemini verified: Fidlar AVA. |
| 12 | Clark | CS | https://clark.oh.publicsearch.us/ | ✅ | Gemini verified: GovOS Cloud Search. |
| 13 | Clermont | CF ✏️ | https://clermontoh-recorder.govos.com/ | ❌ | *URL corrected* — county subdomain, not countyfusion12. CF outage 2026-03-28. |
| 14 | Clinton | **CUS** ✏️ | https://co.clinton.oh.us/ClintonCountyRecordersOnlineRecordsSystem | ✅ | *Was CF* — Gemini verified: custom county portal. |
| 15 | Columbiana | **CUS** ✏️ | https://www.columbianacountyrecorder.org/ | ✅ | *Was CF* — Gemini verified: independent web database. |
| 16 | Coshocton | CF ✏️ | https://countyfusion1.kofiletech.us/ | ❌ | *URL corrected* — kofiletech.us domain (legacy CF). CF outage 2026-03-28. |
| 17 | Crawford | **CUS** ✏️ | https://www.crawfordohrecorder.com/ | ✅ | *Was CF* — Gemini verified: custom recorder site. |
| 18 | Cuyahoga | **CS** ✏️ | https://cuyahoga.oh.publicsearch.us/ | ✅ | *Was CUS/RecorderWorks* — Gemini verified: GovOS Cloud Search, records 1810–present. |
| 19 | Darke | **AVA** ✏️ | https://rep2laredo.fidlar.com/OHDarke/AvaWeb/ | ✅ | *Was CF* — Gemini verified: Fidlar AVA. Key Example Township adjacent county. |
| 20 | Defiance | **AVA** ✏️ | https://defiance-county.com/recorder/index.php | ✅ | *Was CF* — Gemini verified: Fidlar AVA. |
| 21 | Delaware | CUS | https://recorder.co.delaware.oh.us/records-search-page/ | ✅ | Gemini verified: custom county portal. |
| 22 | Erie | **EAG** ✏️ | https://eriecountyoh-selfservice.tylerhost.net/web/ | ✅ | *Was CF* — Gemini verified: Tyler EagleWeb (tylerhost.net). |
| 23 | Fairfield | **AVA** ✏️ | https://ava.fidlar.com/OHFairfield/AvaWeb/ | ✅ | *Was CF* — Gemini verified: Fidlar AVA, includes legacy deed index. |
| 24 | Fayette | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=FayetteOH | ❌ | CF platform outage 2026-03-28 |
| 25 | Franklin | CS ✏️ | https://franklin.oh.publicsearch.us/ | ✅ | *URL corrected* — Gemini verified: GovOS Cloud Search. |
| 26 | Fulton | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=FultonOH | ❌ | CF platform outage 2026-03-28 |
| 27 | Gallia | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=GalliaOH | ❌ | CF platform outage 2026-03-28 |
| 28 | Geauga | **AVA** ✏️ | https://ava.fidlar.com/OHGeauga/AvaWeb/ | ✅ | *Was CF* — Gemini verified: Fidlar AVA. |
| 29 | Greene | **CS** ✏️ | https://greene.oh.publicsearch.us/ | ✅ | *Was CF* — Gemini verified: GovOS Cloud Search. |
| 30 | Guernsey | CF ✏️ | https://countyfusion9.kofiletech.us/countyweb/loginDisplay.action?countyname=GuernseyOH | ❌ | *URL corrected* — kofiletech.us domain. CF outage 2026-03-28. |
| 31 | Hamilton | **CUS** ✏️ | https://acclaim-web.hamiltoncountyohio.gov/AcclaimWebLive/ | ✅ | *Was CF* — Gemini verified: Acclaim-Web custom system. Unaffected by GovOS outage. |
| 32 | Hancock | **CUS** ✏️ | https://recorder.co.hancock.oh.us/ | ✅ | *Was CF* — Gemini verified: custom county portal, index 1985–present. |
| 33 | Hardin | CF ✏️ | https://countyfusion10.kofiletech.us/countyweb/loginDisplay.action?countyname=HardinOH | ❌ | *URL corrected* — kofiletech.us domain. CF outage 2026-03-28. |
| 34 | Harrison | **CS** ✏️ | https://harrison.oh.publicsearch.us/ | ✅ | *Was CF* — Gemini verified: GovOS Cloud Search, images 2008–present. |
| 35 | Henry | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=HenryOH | ❌ | CF platform outage 2026-03-28 |
| 36 | Highland | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=HighlandOH | ❌ | Connector correct — confirmed on CF (FraudSleuth active). Down due to platform outage only. |
| 37 | Hocking | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=HockingOH | ❌ | CF platform outage 2026-03-28 |
| 38 | Holmes | **AVA** ✏️ | https://ava.fidlar.com/OHHolmes/AvaWeb/ | ✅ | *Was LAR* — Gemini verified: Fidlar AVA. |
| 39 | Huron | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=HuronOH | ❌ | CF platform outage 2026-03-28 |
| 40 | Jackson | **CUS** ✏️ | https://www.jacksoncountyohio.us/elected-officials/recorder/ | ✅ | *Was CF* — Gemini verified: custom portal, registration needed for images. |
| 41 | Jefferson | **CS** ✏️ | https://jefferson.oh.publicsearch.us/ | ✅ | *Was CF* — Gemini verified: GovOS Cloud Search, images 2008–present. |
| 42 | Knox | **COTT** ✏️ | https://cotthosting.com/OHKnoxLANExternal/HTML5Viewer/ImageViewer.aspx?OIB=true | ✅ | *Was CF* — Gemini verified: Cott Systems. Not affected by GovOS outage. |
| 43 | Lake | **AVA** ✏️ | https://ava.fidlar.com/OHLake/AvaWeb/ | ✅ | *Was LAR* — Gemini verified: Fidlar AVA. |
| 44 | Lawrence | **COTT** ✏️ | https://cotthosting.com/OHLawrenceExternal/LandRecords/protected/v4/SrchName.aspx | ✅ | *Was CF* — Gemini verified: Cott Systems. Stable. |
| 45 | Licking | **DTS** ✏️ | https://apps.lickingcounty.gov/recorder/paxworld/ | ✅ | *Was CF* — Gemini verified: DTS PAXWorld. Stable. |
| 46 | Logan | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=LoganOH | ❌ | CF platform outage 2026-03-28 |
| 47 | Lorain | **DTS** ✏️ | https://recorder.dts-oh-lorain.com/paxworld/ | ✅ | *Was CF* — Gemini verified: DTS PAXWorld. Fully operational. |
| 48 | Lucas | **DTS** ✏️ | https://lucas.dts-oh.com/PaxWorld5/ | ✅ | *Was CF* — Gemini verified: DTS PAXWorld5. |
| 49 | Madison | USL ✏️ | https://madisonoh.avenuinsights.com/ | ✅ | Gemini verified: Avenu Insights. Stable. |
| 50 | Mahoning | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=MahoningOH | ❌ | CF platform outage 2026-03-28 |
| 51 | Marion | **AVA** ✏️ | https://ava.fidlar.com/OHMarion/AvaWeb/ | ✅ | *Was CF* — Gemini verified: Fidlar AVA. |
| 52 | Medina | **CUS** ✏️ | https://recorder.co.medina.oh.us/ | ✅ | *Was CF* — Gemini verified: custom county-hosted portal. |
| 53 | Meigs | **CUS** ✏️ | https://meigsoh.compiled-technologies.com/Default.aspx | ✅ | *Was CF* — Gemini verified: Compiled Technologies portal. |
| 54 | Mercer | **AVA** ✏️ | https://ava.fidlar.com/OHMercer/AvaWeb/ | ✅ | **KEY COUNTY — Example Township investigation.** *Was CF* — Gemini verified: Fidlar AVA. Now accessible! |
| 55 | Miami | **AVA** ✏️ | https://ava.fidlar.com/OHMiami/AvaWeb/ | ✅ | *Was LAR* — Gemini verified: Fidlar AVA. |
| 56 | Monroe | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=MonroeOH | ❌ | CF platform outage 2026-03-28 |
| 57 | Montgomery | **CUS** ✏️ | https://riss.mcrecorder.org/ | ✅ | *Was CF* — Gemini verified: RISS (Regional Information Systems). Stable. |
| 58 | Morgan | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=MorganOH | ❌ | CF platform outage 2026-03-28 |
| 59 | Morrow | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=MorrowOH | ❌ | CF platform outage 2026-03-28 |
| 60 | Muskingum | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=MuskingumOH | ❌ | CF platform outage 2026-03-28 |
| 61 | Noble | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=NobleOH | ❌ | CF platform outage 2026-03-28 |
| 62 | Ottawa | CS | https://ottawa.oh.publicsearch.us/ | ✅ | Gemini verified: GovOS Cloud Search. |
| 63 | Paulding | **AVA** ✏️ | https://ava.fidlar.com/OHPaulding/AvaWeb/ | ✅ | *Was USL* — Gemini verified: Fidlar AVA. |
| 64 | Perry | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=PerryOH | ❌ | CF platform outage 2026-03-28 |
| 65 | Pickaway | **CUS** ✏️ | https://pickawaycountyrecorder.com/ | ✅ | *Was CF* — Gemini verified: new independent custom portal. |
| 66 | Pike | USL | https://pikeohpublic.avenuinsights.com/ | ✅ | Gemini verified: Avenu Insights. Stable. |
| 67 | Portage | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=PortageOH | ❌ | CF platform outage 2026-03-28 |
| 68 | Preble | CF ✏️ | https://countyfusion9.kofiletech.us/countyweb/loginDisplay.action?countyname=PrebleOH | ❌ | *URL corrected* — kofiletech.us domain confirmed. CF outage 2026-03-28. |
| 69 | Putnam | CF ✏️ | https://countyfusion14.kofiletech.us/countyweb/loginDisplay.action?countyname=PutnamOH | ❌ | *URL corrected* — kofiletech.us domain confirmed. CF outage 2026-03-28. |
| 70 | Richland | **CF** ✏️ | https://countyfusion13.kofiletech.us/countyweb/loginDisplay.action?countyname=RichlandOH | ❌ | *Was USL* — Gemini verified: CountyFusion 13 (kofiletech.us). CF outage 2026-03-28. |
| 71 | Ross | **CUS** ✏️ | https://co.ross.oh.us/recorder/document-archive.html | ✅ | *Was CF* — Gemini verified: custom digital platform. Stable. |
| 72 | Sandusky | **CF** ✏️ | https://countyfusion14.kofiletech.us/countyweb/loginDisplay.action?countyname=SanduskyOH | ❌ | *Was CS* — Gemini verified: CountyFusion 14. CF outage 2026-03-28. |
| 73 | Scioto | **AVA** ✏️ | https://ohscioto.fidlar.com/OHScioto/AvaWeb/ | ✅ | *Was CF* — Gemini verified: Fidlar AVA. |
| 74 | Seneca | CF | https://countyfusion13.govos.com/countyweb/loginDisplay.action?countyname=Seneca | ❌ | **KEY COUNTY — Example Township investigation.** CF outage 2026-03-28. Re-test when back. |
| 75 | Shelby | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=ShelbyOH | ❌ | CF platform outage 2026-03-28 |
| 76 | Stark | **DTS** ✏️ | https://recordersearch.starkcountyohio.gov/paxworld/ | ✅ | *Was CF* — Gemini verified: DTS PAXWorld. Fully operational. |
| 77 | Summit | **EAG** ✏️ | https://eagleweb.summitoh.net/recorder/web/ | ✅ | *Was CF* — Gemini verified: Tyler EagleWeb. Stable. |
| 78 | Trumbull | **DTS** ✏️ | https://records.co.trumbull.oh.us/PAXWorld/views/search | ✅ | *Was CF* — Gemini verified: DTS PAXWorld. Migrated May 2023. Confirmed working without VPN. |
| 79 | Tuscarawas | **CF** ✏️ | https://countyfusion10.kofiletech.us/countyweb/loginDisplay.action?countyname=TuscarawasOH | ❌ | *Was USL* — Gemini verified: CountyFusion 10 (kofiletech.us). CF outage 2026-03-28. |
| 80 | Union | CUS | https://www.unioncountyohio.gov/recorder-disclaimer | ✅ | Gemini verified: custom secure portal. Operational. |
| 81 | Van Wert | CF | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=VanWertOH | ❌ | CF platform outage 2026-03-28 |
| 82 | Vinton | **AVA** ✏️ | https://ohvinton.fidlar.com/OHVinton/AvaWeb/ | ✅ | *Was CF* — Gemini verified: Fidlar AVA. |
| 83 | Warren | **CS** ✏️ | https://warren.oh.publicsearch.us/ | ✅ | *Was LAR* — Gemini verified: GovOS Cloud Search. |
| 84 | Washington | **CS** ✏️ | https://washington.oh.publicsearch.us/ | ✅ | *Was CF* — Gemini verified: GovOS Cloud Search. |
| 85 | Wayne | **CF** ✏️ | https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=WayneOH | ❌ | *Was USL* — Gemini verified: CountyFusion. CF outage 2026-03-28. |
| 86 | Williams | **AVA** ✏️ | https://ohwilliams.fidlar.com/OHWilliams/AvaWeb/ | ✅ | *Was CF* — Gemini verified: Fidlar AVA. |
| 87 | Wood | **AVA** ✏️ | https://ava.fidlar.com/OHWood/AvaWeb/ | ✅ | *Was LAR* — Gemini verified: Fidlar AVA. |
| 88 | Wyandot | **AVA** ✏️ | https://ava.fidlar.com/OHWyandot/AvaWeb/ | ✅ | *Was CF* — Gemini verified: Fidlar AVA. |

---

## Connector Corrections — Status

✏️ = corrected in `county_recorder_connector.py` on 2026-03-28

- [x] **Adams** — ✏️ Fixed: CF → DTS PAXWorld (`https://adams.dts-oh.com/PaxWorld/`)
- [x] **Allen** — ✏️ Fixed: CF → DTS PAXWorld (`https://recorderexternal.allencountyohio.com/paxworld/`)
- [x] **Clinton** — ✏️ Fixed: CF → Custom (`https://co.clinton.oh.us/ClintonCountyRecordersOnlineRecordsSystem`)
- [x] **Hancock** — ✏️ Fixed: stale `kofiletech.us` URL updated to `govos.com`
- [x] **Highland** — ✏️ Updated notes with FraudSleuth detail + corrected phone number
- [x] **Licking** — ✏️ Fixed: CF → DTS PAXWorld (`https://apps.lickingcounty.gov/recorder/paxworld/`)
- [x] **Lorain** — ✏️ Fixed: CF → DTS PAXWorld (`https://recorder.dts-oh-lorain.com/paxworld/`)
- [x] **Lucas** — ✏️ Fixed: CF → DTS PAXWorld5 (`https://lucas.dts-oh.com/PaxWorld5/`)
- [x] **Stark** — ✏️ Fixed: CF → DTS PAXWorld (`https://recordersearch.starkcountyohio.gov/paxworld/`)
- [x] **Summit** — ✏️ Fixed: CF → EagleWeb/Custom (`https://eagleweb.summitoh.net/recorder/web/`)
- [x] **Trumbull** — ✏️ Fixed: CF → DTS PAXWorld (`https://records.co.trumbull.oh.us/PAXWorld/views/search`)
- [x] **RecorderSystem enum** — ✏️ Added `DTS_PAXWORLD = "DTS PAXWorld"` value

---

## DTS PAXWorld — Access Notes

DTS PAXWorld is hosted by **Document Technology Systems (DTS)**, an Ohio-based vendor. Counties either host it on the `dts-oh.com` domain or on their own county subdomain (like Trumbull's `records.co.trumbull.oh.us`).

**Important finding:** Trumbull's PAXWorld URL (`records.co.trumbull.oh.us`) also times out without VPN, suggesting DTS-hosted county sites may have IP restrictions or require direct network access. This needs to be verified — it may be a network configuration issue on Trumbull's end specifically, or it may be a broader DTS platform issue.

The connector should be updated to add `DTS_PAXWORLD` as a new `RecorderSystem` enum value, with appropriate notes about potential access issues.

---

## Next Steps

### Immediate (waiting on CountyFusion outage to resolve)
- [ ] Wait for GovOS CountyFusion platform to come back online — all CF counties untestable until then
- [ ] Once CF is back, re-test Seneca, Mercer, and other key investigation counties
- [ ] Check GovOS status page or contact GovOS support if outage persists: https://www.govos.com/

### Connector corrections (confirmed, ready to do now)
- [ ] Add `DTS_PAXWORLD` as a new `RecorderSystem` enum value in `county_recorder_connector.py`
- [ ] Update **Trumbull** → DTS PAXWorld, `https://records.co.trumbull.oh.us/PAXWorld/views/search`
- [ ] Update **Adams** → DTS PAXWorld, `https://adams.dts-oh.com/PaxWorld/`
- [ ] Update **Allen** → DTS PAXWorld, `https://recorderexternal.allencountyohio.com/paxworld/`
- [ ] Update **Licking** → DTS PAXWorld, `https://apps.lickingcounty.gov/recorder/paxworld/`
- [ ] Update **Lorain** → DTS PAXWorld, `https://recorder.dts-oh-lorain.com/paxworld/`
- [ ] Update **Lucas** → DTS PAXWorld, `https://lucas.dts-oh.com/PaxWorld5/`
- [ ] Update **Stark** → DTS PAXWorld, `https://recordersearch.starkcountyohio.gov/paxworld/`
- [ ] Update **Summit** → EagleWeb, `https://eagleweb.summitoh.net/recorder/web/`
- [ ] Update **Clinton** → Custom, `https://co.clinton.oh.us/ClintonCountyRecordersOnlineRecordsSystem`

### Remaining research
- [ ] Fill in `*(check connector)*` entries by reading the full connector registry (lines 370–1100)
- [ ] Research any additional Ohio counties that may have migrated off CountyFusion since the connector was built
- [ ] Consider adding a `vpn_required` flag to `CountyInfo` for portals with known access restrictions

---

*Sources: [WFMJ — Ohio auditor reviewing Trumbull recorder/DTS vendor](https://www.wfmj.com/story/53369996/ohio-auditor-reviewing-request-to-investigate-former-trumbull-co-recorder-software-vendor) · [Ohio Recorders' Association](https://www.ohiorecorders.com/by-county-name/) · [NETR Online Ohio](https://publicrecords.netronline.com/state/OH)*
