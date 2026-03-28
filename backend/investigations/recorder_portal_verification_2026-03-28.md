# Ohio County Recorder Portal Verification — 2026-03-28

## Confidence Score Model

| Component | Max Points | Description |
|-----------|-----------|-------------|
| HTTP Reachability | 35 | 200 no-redirect=35, same-domain redirect=25, cross-domain=15, error=0 |
| Domain Pattern Match | 25 | Final URL domain matches expected pattern for RecorderSystem |
| Page Content | 20 | Page text contains recorder-specific keywords (grantor, grantee, deed, etc.) |
| URL Source | 20 | User-confirmed=20, pattern-confirmed=15, Gemini-sourced=5–10 |

| Tier | Score | Meaning |
|------|-------|---------|
| 🟢 HIGH | 80–100 | Trust this URL. Verified working. |
| 🟡 MEDIUM | 50–79 | Probably right — spot-check before relying on it. |
| 🟠 LOW | 25–49 | Significant doubts. Manual verification needed. |
| 🔴 CRITICAL | 0–24 | Do not use. Likely dead, wrong, or pointing to aggregator. |

---

## Summary

| Tier | Count |
|------|-------|
| 🔴 CRITICAL | 0 |
| 🟠 LOW | 0 |
| 🟡 MEDIUM | 15 |
| 🟢 HIGH | 43 |
| ⏭️  SKIPPED (CountyFusion — outage) | 30 |
| **Total** | **88** |

---

## 🔴 CRITICAL — Fix Immediately

_Score 0–24. These URLs are dead, redirect to aggregators, or have no recorder content._

_None._

---

## 🟠 LOW Confidence — Manual Verification Needed

_Score 25–49. URL loads but domain, content, or source raises concerns._

_None._

---

## 🟡 MEDIUM Confidence — Spot-Check Recommended

_Score 50–79. Structurally correct but not fully verified by live user session._

| County | System | Score | Flags | URL |
|--------|--------|-------|-------|-----|
| Adams | Custom/Other | 75 | — | `https://adamscountyoh.gov/recorder/` |
| Athens | Fidlar AVA | 70 | NO_RECORDER_KEYWORDS | `https://ohathens.fidlar.com/OHAthens/AvaWeb/` |
| Auglaize | Custom/Other | 75 | — | `http://gis.auglaizecounty.org/scanneddrawings/` |
| Clinton | Custom/Other | 75 | — | `https://co.clinton.oh.us/ClintonCountyRecordersOnlineRecordsSystem` |
| Darke | Fidlar AVA | 70 | NO_RECORDER_KEYWORDS | `https://rep2laredo.fidlar.com/OHDarke/AvaWeb/` |
| Defiance | Fidlar AVA | 60 | DOMAIN_MISMATCH | `https://defiance-county.com/recorder/index.php` |
| Erie | EagleWeb (Tyler) | 70 | NO_RECORDER_KEYWORDS | `https://eriecountyoh-selfservice.tylerhost.net/web/` |
| Fairfield | Fidlar AVA | 70 | NO_RECORDER_KEYWORDS | `https://ava.fidlar.com/OHFairfield/AvaWeb/` |
| Geauga | Fidlar AVA | 70 | NO_RECORDER_KEYWORDS | `https://ava.fidlar.com/OHGeauga/AvaWeb/` |
| Paulding | Fidlar AVA | 70 | NO_RECORDER_KEYWORDS | `https://ava.fidlar.com/OHPaulding/AvaWeb/` |
| Scioto | Fidlar AVA | 70 | NO_RECORDER_KEYWORDS | `https://ohscioto.fidlar.com/OHScioto/AvaWeb/` |
| Union | Custom/Other | 75 | — | `https://www.unioncountyohio.gov/recorder-disclaimer` |
| Vinton | Fidlar AVA | 70 | NO_RECORDER_KEYWORDS | `https://ohvinton.fidlar.com/OHVinton/AvaWeb/` |
| Williams | Fidlar AVA | 70 | NO_RECORDER_KEYWORDS | `https://ohwilliams.fidlar.com/OHWilliams/AvaWeb/` |
| Wyandot | Fidlar AVA | 70 | NO_RECORDER_KEYWORDS | `https://ava.fidlar.com/OHWyandot/AvaWeb/` |

---

## 🟢 HIGH Confidence — Verified

_Score 80–100. URL confirmed working with recorder content present._

| County | System | Score | URL |
|--------|--------|-------|-----|
| Allen | DTS PAXWorld | 84 | `https://recorderexternal.allencountyohio.com/paxworld/` |
| Ashtabula | Cott Systems | 85 | `https://cotthosting.com/ohashtabula/User/Login.aspx` |
| Belmont | Custom/Other | 90 | `https://belmontcountyrecorder.org/` |
| Brown | Custom/Other | 84 | `https://www.browncountyohio.gov/index.php/recorder44` |
| Butler | GovOS Cloud Search | 100 | `https://butler.oh.publicsearch.us/` |
| Carroll | GovOS Cloud Search | 100 | `https://carroll.oh.publicsearch.us/` |
| Champaign | Custom/Other | 85 | `https://champaigncountyrecorder.us/` |
| Clark | GovOS Cloud Search | 95 | `https://clark.oh.publicsearch.us/` |
| Columbiana | Custom/Other | 90 | `https://www.columbianacountyrecorder.org/` |
| Crawford | Compiled Technologies | 80 | `https://crawfordoh.compiled-technologies.com/Default.aspx` |
| Cuyahoga | GovOS Cloud Search | 100 | `https://cuyahoga.oh.publicsearch.us/` |
| Delaware | Custom/Other | 90 | `https://recorder.co.delaware.oh.us/records-search-page/` |
| Franklin | GovOS Cloud Search | 100 | `https://franklin.oh.publicsearch.us/` |
| Greene | GovOS Cloud Search | 95 | `https://greene.oh.publicsearch.us/` |
| Hamilton | Custom/Other | 80 | `https://acclaim-web.hamiltoncountyohio.gov/AcclaimWebLive/` |
| Hancock | Custom/Other | 80 | `https://www.co.hancock.oh.us/196/Record-Search` |
| Harrison | GovOS Cloud Search | 95 | `https://harrison.oh.publicsearch.us/` |
| Holmes | Fidlar AVA | 80 | `https://ohholmes.fidlar.com/OHHolmes/AvaWeb/` |
| Jackson | Custom/Other | 90 | `https://www.jacksoncountyohio.us/elected-officials/recorder/` |
| Jefferson | GovOS Cloud Search | 95 | `https://jefferson.oh.publicsearch.us/` |
| Knox | Cott Systems | 84 | `https://cotthosting.com/OHKnoxLANExternal/LandRecords/protected/v4/SrchName.aspx` |
| Lake | Fidlar AVA | 80 | `https://rep2laredo.fidlar.com/OHLake/AvaWeb/#/search` |
| Lawrence | Cott Systems | 89 | `https://cotthosting.com/OHLawrenceExternal/LandRecords/protected/v4/SrchName.aspx` |
| Licking | DTS PAXWorld | 84 | `https://apps.lickingcounty.gov/recorder/paxworld/` |
| Lorain | DTS PAXWorld | 90 | `https://recorder.dts-oh-lorain.com/paxworld/` |
| Lucas | DTS PAXWorld | 84 | `https://lucas.dts-oh.com/PaxWorld5/` |
| Madison | USLandRecords (Avenu) | 94 | `https://madisonoh.avenuinsights.com/Home/index.html` |
| Marion | Fidlar AVA | 80 | `https://rep3laredo.fidlar.com/OHMarion/AvaWeb/` |
| Medina | Custom/Other | 84 | `https://recorder.co.medina.oh.us/` |
| Meigs | Compiled Technologies | 85 | `https://meigsoh.compiled-technologies.com/Default.aspx` |
| Mercer | Custom/Other | 100 | `https://recorder.mercercountyoh.gov/LandmarkWeb/` |
| Miami | Laredo (Fidlar) | 80 | `https://rep4laredo.fidlar.com/OHMiami/DirectSearch/#/search` |
| Montgomery | Custom/Other | 84 | `https://riss.mcrecorder.org/` |
| Ottawa | GovOS Cloud Search | 95 | `https://ottawa.oh.publicsearch.us/` |
| Pickaway | Custom/Other | 80 | `https://pickawaycountyrecorder.com/` |
| Pike | Custom/Other | 80 | `https://pikeohpublic.avenuinsights.com/` |
| Ross | Custom/Other | 90 | `https://www.rossrecords.us/` |
| Stark | Custom/Other | 85 | `https://starkcountyohio.gov/government/offices/recorder/` |
| Summit | EagleWeb (Tyler) | 84 | `https://summitcountyoh-web.tylerhost.net/web/search/DOCSEARCH236S2` |
| Trumbull | DTS PAXWorld | 84 | `https://records.co.trumbull.oh.us/PAXWorld/views/search` |
| Warren | Fidlar AVA | 80 | `https://ohwarren.fidlar.com/OHWarren/AvaWeb/` |
| Washington | GovOS Cloud Search | 95 | `https://washington.oh.publicsearch.us/` |
| Wood | Fidlar AVA | 80 | `https://ohwood.fidlar.com/OHWood/AvaWeb/` |

---

## ⏭️  Skipped (CountyFusion — Platform Outage)

_These counties use GovOS CountyFusion which has been down since 2026-03-28._
_Re-run with `--include-cf` once GovOS recovers to verify their URLs._

| County | URL |
|--------|-----|
| Ashland | `https://countyfusion10.kofiletech.us/countyweb/loginDisplay.action?countyname=AshlandOH` |
| Clermont | `https://clermontoh-recorder.govos.com/` |
| Coshocton | `https://countyfusion1.kofiletech.us/` |
| Fayette | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=FayetteOH` |
| Fulton | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=FultonOH` |
| Gallia | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=GalliaOH` |
| Guernsey | `https://countyfusion9.kofiletech.us/countyweb/loginDisplay.action?countyname=GuernseyOH` |
| Hardin | `https://countyfusion10.kofiletech.us/countyweb/loginDisplay.action?countyname=HardinOH` |
| Henry | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=HenryOH` |
| Highland | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=HighlandOH` |
| Hocking | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=HockingOH` |
| Huron | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=HuronOH` |
| Logan | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=LoganOH` |
| Mahoning | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=MahoningOH` |
| Monroe | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=MonroeOH` |
| Morgan | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=MorganOH` |
| Morrow | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=MorrowOH` |
| Muskingum | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=MuskingumOH` |
| Noble | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=NobleOH` |
| Perry | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=PerryOH` |
| Portage | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=PortageOH` |
| Preble | `https://countyfusion9.kofiletech.us/countyweb/loginDisplay.action?countyname=PrebleOH` |
| Putnam | `https://countyfusion14.kofiletech.us/countyweb/loginDisplay.action?countyname=PutnamOH` |
| Richland | `https://countyfusion13.kofiletech.us/countyweb/loginDisplay.action?countyname=RichlandOH` |
| Sandusky | `https://countyfusion14.kofiletech.us/countyweb/loginDisplay.action?countyname=SanduskyOH` |
| Seneca | `https://countyfusion13.govos.com/countyweb/loginDisplay.action?countyname=Seneca` |
| Shelby | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=ShelbyOH` |
| Tuscarawas | `https://countyfusion10.kofiletech.us/countyweb/loginDisplay.action?countyname=TuscarawasOH` |
| Van Wert | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=VanWertOH` |
| Wayne | `https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=WayneOH` |

---

## How to Fix CRITICAL / LOW Counties

1. Go to the county's official `.oh.gov` or `.oh.us` website
2. Navigate: County website → Recorder → Online Records / Document Search
3. Follow any links from the recorder's own page to the search portal
4. Record the final URL the recorder's office uses (not Google/aggregator results)
5. Update `county_recorder_connector.py` with the correct URL and system
6. Add the URL to `USER_CONFIRMED_URLS` in this script so future runs score it HIGH

**Do NOT use Google search results or aggregator sites to find recorder URLs.**
**Always follow the official county government path.**