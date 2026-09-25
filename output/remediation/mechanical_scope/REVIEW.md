# E4 scope decisions - per-site review

Built 2026-09-25T07:20:53+00:00 from the production export of 2026-09-25 07:16:05.821323+00. Read this before `apply.py --lane scope-e4 --apply`: every row below becomes two journalled cells (`scope_status`, `scope_reason`). `retired` hides the site everywhere a visitor, a crawler or a card draw reaches it; `pending` keeps it shown and flags it; `in_scope` records the decision to keep it. T11 ran over the live export, not the 2026-09-20 snapshot its evidence lines are labelled with (`snapshot:unified_sites...` is T11's wording for the rows it was given).

What this lane does not do: it moves nothing. A retired duplicate keeps its images and content links; where the survivor has fewer (the counts are on each line below), moving them is a follow-up before the survivor's page is relied on. A `pending` row stays shown until its date or scope is settled - the evidence says what to settle.

## (a) outside the E3 window by the current period_start - 57 site(s)

### retired (54)

* **Ali Masjid Fort** (`8c159d7f-d954-44fc-aab9-6b7841d68a35`) - Pakistan, Fortress/citadel, period_start 1837, 4 link(s), 8 image(s)
  * reason: E3: period_start 1837 is 1337 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 71.2569792098065, date = 1837]
  * snapshot:unified_sites.period_start: period_start = 1837, period_end = None, period_name = '1500+ AD', lat = 34.033406022144014, lon = 71.2569792098065
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Pakistan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Attock Fort** (`cf7e7df8-8987-4989-9fd5-d506d1844669`) - Pakistan, Fortress/citadel, period_start 1580, 4 link(s), 20 image(s)
  * reason: E3: period_start 1580 is 1080 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 72.23744014098035, date = 1580]
  * snapshot:unified_sites.period_start: period_start = 1580, period_end = None, period_name = '1500+ AD', lat = 33.89138501659671, lon = 72.23744014098035
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Pakistan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Bayer's Lake Mystery Walls** (`2fb9ef2d-55be-497a-9759-735df4f80db8`) - Canada, Wall, period_start 1760, 4 link(s), 1 image(s)
  * reason: E3: period_start 1760 is 260 years past the Americas cutoff of 1500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 1500 (Americas); return date <= cutoff   [lon = -63.658978544286235, date = 1760]
  * snapshot:unified_sites.period_start: period_start = 1760, period_end = None, period_name = '1500+ AD', lat = 44.6430915816845, lon = -63.658978544286235
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Canada; CONTINENT = North America; region agrees with the longitude window (Americas)
* **Belenkeşlik Castle** (`42ddb06e-547a-4f8e-b093-a6efcf2a8e2c`) - Türkiye, Fortress/citadel, period_start 1100, 2 link(s), 1 image(s)
  * reason: E3: period_start 1100 is 600 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 34.553743502498584, date = 1100]
  * snapshot:unified_sites.period_start: period_start = 1100, period_end = None, period_name = '1000 - 1500 AD', lat = 36.97243357399953, lon = 34.553743502498584
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Turkey; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Bhagwan Bharat's Statue** (`59267588-ef6b-40b7-9990-c93b2b6d08f4`) - India, Monument, period_start 900, 3 link(s), 0 image(s)
  * reason: E3: period_start 900 is 400 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 76.48693174482743, date = 900]
  * snapshot:unified_sites.period_start: period_start = 900, period_end = None, period_name = '500 - 1000 AD', lat = 12.861775954431037, lon = 76.48693174482743
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: India; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Buddhist Rock Carving in Manglawar** (`916b8b05-0c42-4af3-b05e-9be842a23c5b`) - Pakistan, Rock relief/carving, period_start 600, 4 link(s), 10 image(s)
  * reason: E3: period_start 600 is 100 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 72.43103056539427, date = 600]
  * snapshot:unified_sites.period_start: period_start = 600, period_end = None, period_name = '500 - 1000 AD', lat = 34.80835923228664, lon = 72.43103056539427
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Pakistan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Chagres and Fort San Lorenzo** (`6991377d-fbb5-4c0b-9e24-6dc294033fda`) - Panama, City/town/settlement, period_start 1590, 0 link(s), 20 image(s)
  * reason: E3: period_start 1590 is 90 years past the Americas cutoff of 1500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 1500 (Americas); return date <= cutoff   [lon = -80.00284217739622, date = 1590]
  * snapshot:unified_sites.period_start: period_start = 1590, period_end = None, period_name = '1500+ AD', lat = 9.322486869144173, lon = -80.00284217739622
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: no feature (open water); CONTINENT = n/a; no second opinion available
  * remediation_change_log:29288: phase3:batch-0266:chunk-0001: period_start 1000 -> 1590
* **Charents Arch** (`a9d840ac-4636-40bf-9570-682550967728`) - Armenia, Monument, period_start 1957, 0 link(s), 20 image(s)
  * reason: E3: period_start 1957 is 1457 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 44.637031089005326, date = 1957]
  * snapshot:unified_sites.period_start: period_start = 1957, period_end = None, period_name = '1500+ AD', lat = 40.17379806070865, lon = 44.637031089005326
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Armenia; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Chrobry Fortified Village** (`a26993c6-b562-4c28-a584-8de2c9312dad`) - Poland, Monument, period_start 1000, 0 link(s), 2 image(s)
  * reason: E3: period_start 1000 is 500 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 15.517510726059847, date = 1000]
  * snapshot:unified_sites.period_start: period_start = 1000, period_end = None, period_name = '1000 - 1500 AD', lat = 51.55761336895247, lon = 15.517510726059847
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Poland; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Dara Fortress** (`f993864c-339b-4a13-b85c-59a59737df2c`) - Türkiye, Fortress, period_start 750, 0 link(s), 0 image(s)
  * reason: E3: period_start 750 is 250 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 40.94817961, date = 750]
  * snapshot:unified_sites.period_start: period_start = 750, period_end = None, period_name = '500 - 1000 AD', lat = 37.17779994, lon = 40.94817961
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Turkey; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **East Bay Walls** (`5f8ce412-3bb0-4aa3-aff3-cd1d825273a6`) - USA, Megalithic walls, period_start 1850, 5 link(s), 2 image(s)
  * reason: E3: period_start 1850 is 350 years past the Americas cutoff of 1500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 1500 (Americas); return date <= cutoff   [lon = -122.9659920339683, date = 1850]
  * snapshot:unified_sites.period_start: period_start = 1850, period_end = None, period_name = '1500+ AD', lat = 38.20569961714214, lon = -122.9659920339683
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: United States of America; CONTINENT = North America; region agrees with the longitude window (Americas)
* **Forte de Nossa Senhora da Graça** (`46bceb53-3c23-41a6-9659-b7a67035197a`) - Portugal, Fortress/citadel, period_start 1763, 0 link(s), 0 image(s)
  * reason: E3: period_start 1763 is 1263 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = -7.163850091954278, date = 1763]
  * snapshot:unified_sites.period_start: period_start = 1763, period_end = None, period_name = '1500+ AD', lat = 38.89474390265923, lon = -7.163850091954278
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Portugal; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Forte de Santa Luzia** (`3ff2ae0e-9095-48ed-a45e-0d8c9f455527`) - Portugal, Fortress/citadel, period_start 1641, 0 link(s), 0 image(s)
  * reason: E3: period_start 1641 is 1141 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = -7.158484243654053, date = 1641]
  * snapshot:unified_sites.period_start: period_start = 1641, period_end = None, period_name = '1500+ AD', lat = 38.87299505487175, lon = -7.158484243654053
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Portugal; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Fortress of Niha** (`a451f6be-a506-41f6-9bf7-85d8c7c7ac8e`) - Lebanon, Fortress/citadel, period_start 975, 5 link(s), 7 image(s)
  * reason: E3: period_start 975 is 475 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 35.60890796441779, date = 975]
  * snapshot:unified_sites.period_start: period_start = 975, period_end = None, period_name = '500 - 1000 AD', lat = 33.57995303701981, lon = 35.60890796441779
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Lebanon; CONTINENT = Asia; region agrees with the longitude window (rest of world)
  * remediation_change_log:28241: phase3:batch-0099:chunk-0001: period_start 1 -> 975
* **Gondrani (Shehr-e-Roghan)** (`f91d645f-29ad-439d-83eb-fdf0531d93cc`) - Pakistan, Cave Structures, period_start 700, 0 link(s), 8 image(s)
  * reason: E3: period_start 700 is 200 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 66.211976321539, date = 700]
  * snapshot:unified_sites.period_start: period_start = 700, period_end = None, period_name = '500 - 1000 AD', lat = 26.394516066518253, lon = 66.211976321539
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Pakistan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Great Kyz Kala** (`78a48265-c951-4c65-b513-f39467b85d50`) - Turkmenistan, Fortress, period_start 750, 0 link(s), 0 image(s)
  * reason: E3: period_start 750 is 250 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 62.152558, date = 750]
  * snapshot:unified_sites.period_start: period_start = 750, period_end = None, period_name = '500 - 1000 AD', lat = 37.65505, lon = 62.152558
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Turkmenistan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Jaffa Gate** (`c932b4f9-283e-4756-b9aa-cc5491aaddf8`) - Israel, Gate/archway/bridge, period_start 1538, 5 link(s), 20 image(s)
  * reason: E3: period_start 1538 is 1038 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 35.22802433664251, date = 1538]
  * snapshot:unified_sites.period_start: period_start = 1538, period_end = None, period_name = '1500+ AD', lat = 31.776773353045204, lon = 35.22802433664251
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Israel; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Jamrud Fort** (`8a42154e-7081-481f-ad77-49e7a02b2c98`) - Pakistan, Fortress/citadel, period_start 1836, 5 link(s), 20 image(s)
  * reason: E3: period_start 1836 is 1336 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 71.37880909553137, date = 1836]
  * snapshot:unified_sites.period_start: period_start = 1836, period_end = None, period_name = '1500+ AD', lat = 34.00366512454234, lon = 71.37880909553137
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Pakistan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Kagoshima Castle Ruins** (`6791baaf-bb36-462b-a497-e704e23251ac`) - Japan, Fortress/citadel, period_start 1601, 5 link(s), 20 image(s)
  * reason: E3: period_start 1601 is 1101 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 130.55598411335166, date = 1601]
  * snapshot:unified_sites.period_start: period_start = 1601, period_end = None, period_name = '1500+ AD', lat = 31.59740183236976, lon = 130.55598411335166
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Japan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Kameishi** (`9b5751dd-d54e-4e8a-b4c0-7b4dc2a863c7`) - Japan, Megalithic stones, period_start 600, 5 link(s), 20 image(s)
  * reason: E3: period_start 600 is 100 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 135.81194581599186, date = 600]
  * snapshot:unified_sites.period_start: period_start = 600, period_end = None, period_name = '500 - 1000 AD', lat = 34.471268019493515, lon = 135.81194581599186
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Japan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Koe Thaung Pagoda** (`e514dc13-8bd1-443b-8137-94ff173d32b8`) - Myanmar, Temple complex, period_start 1554, 5 link(s), 20 image(s)
  * reason: E3: period_start 1554 is 1054 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 93.21197458845535, date = 1554]
  * snapshot:unified_sites.period_start: period_start = 1554, period_end = None, period_name = '1500+ AD', lat = 20.598480658716372, lon = 93.21197458845535
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Myanmar; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Kot Diji Fort** (`98cb1e3f-2eab-4bd0-9cda-8bd61abcacb6`) - Pakistan, Fortress/citadel, period_start 1795, 5 link(s), 20 image(s)
  * reason: E3: period_start 1795 is 1295 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 68.70630495372406, date = 1795]
  * snapshot:unified_sites.period_start: period_start = 1795, period_end = None, period_name = '1500+ AD', lat = 27.34529856511471, lon = 68.70630495372406
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Pakistan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Krishnabai Mandir** (`826407f8-35ca-4423-bd85-5f53a3d95ea2`) - India, Temple complex, period_start 1888, 5 link(s), 0 image(s)
  * reason: E3: period_start 1888 is 1388 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 73.66596936386783, date = 1888]
  * snapshot:unified_sites.period_start: period_start = 1888, period_end = None, period_name = '1500+ AD', lat = 17.964491821550975, lon = 73.66596936386783
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: India; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Ksar el Barka** (`a5d9e9a7-9fd2-4a0f-a3ae-7dd78fba429b`) - Mauritania, City/town/settlement, period_start 1690, 5 link(s), 2 image(s)
  * reason: E3: period_start 1690 is 1190 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = -12.216613060034955, date = 1690]
  * snapshot:unified_sites.period_start: period_start = 1690, period_end = None, period_name = '1500+ AD', lat = 18.400254490856646, lon = -12.216613060034955
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Mauritania; CONTINENT = Africa; region agrees with the longitude window (rest of world)
* **Landguard Fort** (`39f7cab4-e0d9-4c15-a4a0-8fccd461ba3b`) - England, Fortress/citadel, period_start 1540, 5 link(s), 18 image(s)
  * reason: E3: period_start 1540 is 1040 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 1.321099997246992, date = 1540]
  * snapshot:unified_sites.period_start: period_start = 1540, period_end = None, period_name = '1500+ AD', lat = 51.93905871586428, lon = 1.321099997246992
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: no feature (open water); CONTINENT = n/a; no second opinion available
* **Lëkurësi Castle** (`af9036d8-9a13-4107-b22d-b5c088006d91`) - Albania, Castle/palace, period_start 1537, 5 link(s), 20 image(s)
  * reason: E3: period_start 1537 is 1037 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 20.02571291323424, date = 1537]
  * snapshot:unified_sites.period_start: period_start = 1537, period_end = None, period_name = '1500+ AD', lat = 39.866048207174195, lon = 20.02571291323424
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Albania; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Manora Fort, Karachi (Qasim Fort)** (`2dfb1bee-9ec5-4eb6-b8b7-cfedbcb09744`) - Pakistan, Fortress/citadel, period_start 1797, 5 link(s), 3 image(s)
  * reason: E3: period_start 1797 is 1297 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 66.97947658247378, date = 1797]
  * snapshot:unified_sites.period_start: period_start = 1797, period_end = None, period_name = '1500+ AD', lat = 24.79010711991839, lon = 66.97947658247378
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: no feature (open water); CONTINENT = n/a; no second opinion available
* **Midford Castle** (`32429f3c-6e14-4015-900a-a9cd9fbb81eb`) - England, Castle/palace, period_start 1775, 5 link(s), 6 image(s)
  * reason: E3: period_start 1775 is 1275 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = -2.3463889027884193, date = 1775]
  * snapshot:unified_sites.period_start: period_start = 1775, period_end = None, period_name = '1500+ AD', lat = 51.35064268125167, lon = -2.3463889027884193
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: United Kingdom; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Montjuïc Castle** (`ed05c23a-973b-4d69-923c-b2e7b1b97305`) - Spain, Fortress/citadel, period_start 1641, 0 link(s), 18 image(s)
  * reason: E3: period_start 1641 is 1141 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 2.1657341522236093, date = 1641]
  * snapshot:unified_sites.period_start: period_start = 1641, period_end = None, period_name = '1500+ AD', lat = 41.36318446691442, lon = 2.1657341522236093
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Spain; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Mount Livadiyskaya** (`97b3cd09-f833-48ca-8273-8b76767fc245`) - Russia, Natural feature, period_start 698, 5 link(s), 11 image(s)
  * reason: E3: period_start 698 is 198 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 132.6828497963019, date = 698]
  * snapshot:unified_sites.period_start: period_start = 698, period_end = None, period_name = '500 - 1000 AD', lat = 43.06768919119122, lon = 132.6828497963019
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Russia; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Naegi Castle Ruins** (`35e015d9-6ab6-4763-9873-0ff2560b9b91`) - Japan, Castle/palace, period_start 1532, 5 link(s), 20 image(s)
  * reason: E3: period_start 1532 is 1032 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 137.48553198900532, date = 1532]
  * snapshot:unified_sites.period_start: period_start = 1532, period_end = None, period_name = '1500+ AD', lat = 35.514373659160256, lon = 137.48553198900532
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Japan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Naukot Fort** (`bc10d0af-75ab-4c01-8b2c-a00327d0bb80`) - Pakistan, Fortress/citadel, period_start 1810, 0 link(s), 20 image(s)
  * reason: E3: period_start 1810 is 1310 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 69.4498080266548, date = 1810]
  * snapshot:unified_sites.period_start: period_start = 1810, period_end = None, period_name = '1500+ AD', lat = 24.84550170196969, lon = 69.4498080266548
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Pakistan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Nossa Senhora da Boa Estrela** (`46c6cf72-8616-4f4c-8993-73c50abdd6a5`) - Portugal, Monument, period_start 1946, 5 link(s), 0 image(s)
  * reason: E3: period_start 1946 is 1446 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = -7.601288644078303, date = 1946]
  * snapshot:unified_sites.period_start: period_start = 1946, period_end = None, period_name = '1500+ AD', lat = 40.32323381377458, lon = -7.601288644078303
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Portugal; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Olsborg Castle** (`f9ad013b-8208-4a02-8480-7c865c7577f6`) - Sweden, Castle/palace, period_start 1502, 0 link(s), 4 image(s)
  * reason: E3: period_start 1502 is 1002 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 11.34353126882071, date = 1502]
  * snapshot:unified_sites.period_start: period_start = 1502, period_end = None, period_name = '1500+ AD', lat = 58.445434035537524, lon = 11.34353126882071
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Sweden; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Osaka Castle** (`a3fdb1d8-083b-4e8f-a170-5b98638d5b53`) - Japan, Fortress/citadel, period_start 1583, 5 link(s), 20 image(s)
  * reason: E3: period_start 1583 is 1083 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 135.52619503318323, date = 1583]
  * snapshot:unified_sites.period_start: period_start = 1583, period_end = None, period_name = '1500+ AD', lat = 34.68536999989137, lon = 135.52619503318323
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Japan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Oudong** (`37f08947-0576-48de-90ca-ef211b615619`) - Cambodia, City/town/settlement, period_start 1601, 0 link(s), 16 image(s)
  * reason: E3: period_start 1601 is 1101 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 104.74251838714635, date = 1601]
  * snapshot:unified_sites.period_start: period_start = 1601, period_end = None, period_name = '1500+ AD', lat = 11.82398030241317, lon = 104.74251838714635
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Cambodia; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Overton Down** (`414416be-0a81-45f7-a572-216f39ee6a0d`) - England, Geological interest, period_start 1960, 5 link(s), 1 image(s)
  * reason: E3: period_start 1960 is 1460 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = -1.8143429181268396, date = 1960]
  * snapshot:unified_sites.period_start: period_start = 1960, period_end = None, period_name = '1500+ AD', lat = 51.43495380491809, lon = -1.8143429181268396
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: United Kingdom; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Parque Nacional de Shorsky** (`eb80c959-82f5-4288-9a3d-02c2695e583a`) - Russia, Cave Structures, period_start 1989, 3 link(s), 20 image(s)
  * reason: E3: period_start 1989 is 1489 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 88.52799249140432, date = 1989]
  * snapshot:unified_sites.period_start: period_start = 1989, period_end = None, period_name = '1500+ AD', lat = 52.66634033939385, lon = 88.52799249140432
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Russia; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Prambanan Temple** (`21bd525e-fe10-40dd-96be-32d3c8d36d26`) - Indonesia, Temple complex, period_start 850, 0 link(s), 18 image(s)
  * reason: E3: period_start 850 is 350 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 110.49200920619666, date = 850]
  * snapshot:unified_sites.period_start: period_start = 850, period_end = None, period_name = '1 - 500 AD', lat = -7.751765461045863, lon = 110.49200920619666
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Indonesia; CONTINENT = Asia; region agrees with the longitude window (rest of world)
  * remediation_change_log:30897: phase3:gap-0006:chunk-0001: period_start 1 -> 850
* **Preah Palilay** (`41705e94-8ffd-45f3-943e-df6fac317144`) - Cambodia, Temple complex, period_start 1100, 5 link(s), 15 image(s)
  * reason: E3: period_start 1100 is 600 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 103.85504291268045, date = 1100]
  * snapshot:unified_sites.period_start: period_start = 1100, period_end = None, period_name = '1000 - 1500 AD', lat = 13.44909758300017, lon = 103.85504291268045
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Cambodia; CONTINENT = Asia; region agrees with the longitude window (rest of world)
  * remediation_change_log:28290: phase3:batch-0106:chunk-0002: period_start 1 -> 1100
* **Ruther Cross** (`10fc71fe-5305-497e-8642-4219e822223a`) - England, Stone cross, period_start 1200, 0 link(s), 1 image(s)
  * reason: E3: period_start 1200 is 700 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = -1.0675156295788217, date = 1200]
  * snapshot:unified_sites.period_start: period_start = 1200, period_end = None, period_name = '1000 - 1500 AD', lat = 54.52642959256762, lon = -1.0675156295788217
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: United Kingdom; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Sahasralinga** (`075337ec-9108-431f-ae90-d5d0e795f23a`) - India, Petroglyphs, period_start 1678, 5 link(s), 14 image(s)
  * reason: E3: period_start 1678 is 1178 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 74.80794401968993, date = 1678]
  * snapshot:unified_sites.period_start: period_start = 1678, period_end = None, period_name = '1500+ AD', lat = 14.720048880745576, lon = 74.80794401968993
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: India; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Sakafune-ishi Ruins** (`fc029995-b6bb-4375-a5fa-9a0eb7d0fa85`) - Japan, Monument, period_start 655, 5 link(s), 0 image(s)
  * reason: E3: period_start 655 is 155 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 135.82393001784092, date = 655]
  * snapshot:unified_sites.period_start: period_start = 655, period_end = None, period_name = '500 - 1000 AD', lat = 34.47550241309402, lon = 135.82393001784092
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Japan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Shanqal Fort** (`9f823459-f4ce-43cc-a433-b1cdaf9f89ad`) - Saudi Arabia, Fortress/citadel, period_start 1737, 5 link(s), 14 image(s)
  * reason: E3: period_start 1737 is 1237 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 41.65700876887369, date = 1737]
  * snapshot:unified_sites.period_start: period_start = 1737, period_end = None, period_name = '1500+ AD', lat = 21.20023004354095, lon = 41.65700876887369
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Saudi Arabia; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Sheikhupura Fort** (`b9f26550-7988-4a34-a3ff-7ef9cb69c838`) - Pakistan, Fortress/citadel, period_start 1607, 0 link(s), 20 image(s)
  * reason: E3: period_start 1607 is 1107 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 73.98331183854513, date = 1607]
  * snapshot:unified_sites.period_start: period_start = 1607, period_end = None, period_name = '1500+ AD', lat = 31.70021905097919, lon = 73.98331183854513
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Pakistan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Shri Bhagwan Bahubali Monolithic Statue** (`abfa8b60-ea29-4150-925f-87d4b1fe8092`) - India, Megalithic statues, period_start 1973, 0 link(s), 0 image(s)
  * reason: E3: period_start 1973 is 1473 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 75.8679823296231, date = 1973]
  * snapshot:unified_sites.period_start: period_start = 1973, period_end = None, period_name = '1500+ AD', lat = 13.07537316218348, lon = 75.8679823296231
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: India; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Sundarnarayan Temple** (`5067da0a-d681-4fe3-91e5-e2dc7c0656d7`) - India, Temple complex, period_start 1756, 5 link(s), 0 image(s)
  * reason: E3: period_start 1756 is 1256 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 73.79081511174381, date = 1756]
  * snapshot:unified_sites.period_start: period_start = 1756, period_end = None, period_name = '1500+ AD', lat = 20.008369331995894, lon = 73.79081511174381
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: India; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Tomb of Ali Mardan Khan** (`58d46ab0-7fc9-4dfa-bf40-a5042d4a91be`) - Pakistan, Tomb, period_start 1630, 0 link(s), 20 image(s)
  * reason: E3: period_start 1630 is 1130 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 74.36327853854004, date = 1630]
  * snapshot:unified_sites.period_start: period_start = 1630, period_end = None, period_name = '1500+ AD', lat = 31.57403762970014, lon = 74.36327853854004
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Pakistan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Tomb of Jahangir** (`50e5e380-1f89-4fa3-88de-e6ad35241316`) - Pakistan, Tomb, period_start 1627, 5 link(s), 20 image(s)
  * reason: E3: period_start 1627 is 1127 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 74.30326436922896, date = 1627]
  * snapshot:unified_sites.period_start: period_start = 1627, period_end = None, period_name = '1500+ AD', lat = 31.622691826401816, lon = 74.30326436922896
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Pakistan; CONTINENT = Asia; region agrees with the longitude window (rest of world)
* **Ukonkivi** (`eaac27c7-d027-442a-ae0d-49d9e27dfb69`) - Finland, Sacred site, period_start 1100, 0 link(s), 1 image(s)
  * reason: E3: period_start 1100 is 600 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 27.292294869541184, date = 1100]
  * snapshot:unified_sites.period_start: period_start = 1100, period_end = None, period_name = '1000 - 1500 AD', lat = 68.93885103633018, lon = 27.292294869541184
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Finland; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Whiteleaf Cross** (`c54a5e46-c856-46be-b638-62d6fda1c8e5`) - England, Geoglyphs, period_start 1650, 5 link(s), 2 image(s)
  * reason: E3: period_start 1650 is 1150 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = -0.811634516258087, date = 1650]
  * snapshot:unified_sites.period_start: period_start = 1650, period_end = None, period_name = '1500+ AD', lat = 51.72873733243011, lon = -0.811634516258087
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: United Kingdom; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Xhamia e Plumbit** (`e284429d-db64-478d-becd-20faf2a1b847`) - Albania, Mosque, period_start 1733, 4 link(s), 20 image(s)
  * reason: E3: period_start 1733 is 1233 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 19.49995023503225, date = 1733]
  * snapshot:unified_sites.period_start: period_start = 1733, period_end = None, period_name = '1500+ AD', lat = 42.04665187932075, lon = 19.49995023503225
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Albania; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Yenikale Ruins** (`d6d44645-a99b-4826-85b3-eb0123faadd2`) - Ukraine, Fortress/citadel, period_start 1699, 3 link(s), 20 image(s)
  * reason: E3: period_start 1699 is 1199 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 36.60455, date = 1699]
  * snapshot:unified_sites.period_start: period_start = 1699, period_end = None, period_name = '1500+ AD', lat = 45.349449, lon = 36.60455
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Russia; CONTINENT = Europe; region agrees with the longitude window (rest of world)
* **Çem Kalesi** (`0943934a-6b61-416c-a382-8493a2d9db7f`) - Türkiye, Fortress/citadel, period_start 900, 0 link(s), 0 image(s)
  * reason: E3: period_start 900 is 400 years past the rest of world cutoff of 500 AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 36.05023391599186, date = 900]
  * snapshot:unified_sites.period_start: period_start = 900, period_end = None, period_name = '500 - 1000 AD', lat = 37.46346335485921, lon = 36.05023391599186
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Turkey; CONTINENT = Asia; region agrees with the longitude window (rest of world)

### pending (3)

* **Chacamarca Historic Sanctuary** (`160da9ec-9bc4-4893-8066-dd3afb41c5b2`) - Peru, Archaeological site, period_start 1974, 0 link(s), 8 image(s)
  * reason: E3: period_start 1974 is past the cutoff, but the site's own description dates part of it inside the window: period_start 1974 is the protected area's creation; the description names pre-Columbian remains. Plan section 8.2 lists it among the rows that are not museums.
  * unified_sites.description: The sanctuary also protects archaeological remains of the Pumpush culture, an ancient highland civilization of the Bombon Plateau
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 1500 (Americas); return date <= cutoff   [lon = -75.97005364853439, date = 1974]
  * snapshot:unified_sites.period_start: period_start = 1974, period_end = None, period_name = '1500+ AD', lat = -11.216136315002164, lon = -75.97005364853439
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Peru; CONTINENT = South America; region agrees with the longitude window (Americas)
* **Church of the Holy Apostles Peter and Paul, Ras** (`5db5e2c0-081a-4c69-a8c6-6105ac870e5f`) - Serbia, Church/cathedral, period_start 820, 0 link(s), 20 image(s)
  * reason: E3: period_start 820 is past the cutoff, but the site's own description dates part of it inside the window: Phase 3 wrote period_start 1 -> 820; the site's own description says it was founded in the 4th century, inside the window.
  * unified_sites.description: Founded in the 4th century during Roman rule
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 20.526922939078798, date = 820]
  * snapshot:unified_sites.period_start: period_start = 820, period_end = None, period_name = '500 - 1000 AD', lat = 43.16132237189707, lon = 20.526922939078798
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Republic of Serbia; CONTINENT = Europe; region agrees with the longitude window (rest of world)
  * remediation_change_log:28096: phase3:batch-0071:chunk-0001: period_start 1 -> 820
* **Keno Daas Rock Carvings** (`e6f95365-5042-4815-9275-e0e5f295c8e6`) - Pakistan, Rock relief/carving, period_start 600, 5 link(s), 1 image(s)
  * reason: E3: period_start 600 is past the cutoff, but the site's own description dates part of it inside the window: period_start 600 (pre-remediation); the description's range starts in the 5th century, inside the window.
  * unified_sites.description: The region's Buddhist rock art, which peaked between the 5th and 8th centuries AD
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 74.30849225643937, date = 600]
  * snapshot:unified_sites.period_start: period_start = 600, period_end = None, period_name = '500 - 1000 AD', lat = 35.921251921597616, lon = 74.30849225643937
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Pakistan; CONTINENT = Asia; region agrees with the longitude window (rest of world)

## (b) no date - 13 site(s)

### retired (2)

* **Mookambika Wildlife Sanctuary Kodachadri** (`2133d54c-f352-4325-ae0c-dd532f9a65d3`) - India, suspect_modern, period_start None, 5 link(s), 3 image(s)
  * reason: E3: no date, and its own source places it outside the window: Its own source describes a wildlife sanctuary created in 1974 and names no ancient site; the 2026-09-19 assessment listed it among the clear exclusions. site_type holds the marker 'suspect_modern'.
  * unified_sites.description: notified in 1974 and later expanded
  * pipeline/normalizers/dates.py:76-78: date = record.get('period_end') or record.get('period_start'); if date is None: return True  # No date = include (conservative)
  * snapshot:unified_sites: period_start = None, period_end = None, period_name = None
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:59 (1.3): The site is in scope (E3), or flagged as out of scope and hidden.
* **Popping Stone** (`b89bd9e5-053b-4d85-a2a9-1f79a6c3b452`) - England, Geological interest, period_start None, 0 link(s), 2 image(s)
  * reason: E3: no date, and its own source places it outside the window: Natural boulders whose only human history in the source is the 1797 legend; the 2026-09-19 assessment listed it among the clear exclusions.
  * unified_sites.description: centered on the legend that Sir Walter Scott proposed to Charlotte Carpenter at this location in 1797
  * pipeline/normalizers/dates.py:76-78: date = record.get('period_end') or record.get('period_start'); if date is None: return True  # No date = include (conservative)
  * snapshot:unified_sites: period_start = None, period_end = None, period_name = None
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:59 (1.3): The site is in scope (E3), or flagged as out of scope and hidden.

### pending (11)

* **Bosnian Pyramid of Love** (`8df8659c-49be-4a66-b25a-ecbf96541515`) - Bosnia and Herzegovina, Geological interest, period_start None, 4 link(s), 19 image(s)
  * reason: E3: no date, and no source of the row places it outside the window: A natural hill claimed as a pyramid since 2005; the 2026-09-19 assessment left the three Bosnian 'pyramids' to the owner. Not dated by any source, so not retired by rule (b).
  * unified_sites.description: The site has no verified archaeological significance.
  * pipeline/normalizers/dates.py:76-78: date = record.get('period_end') or record.get('period_start'); if date is None: return True  # No date = include (conservative)
  * snapshot:unified_sites: period_start = None, period_end = None, period_name = None
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:59 (1.3): The site is in scope (E3), or flagged as out of scope and hidden.
* **Bosnian Pyramid of the Moon** (`0fd636ac-1a80-4a77-b9d0-a065ae811656`) - Bosnia and Herzegovina, Geological interest, period_start None, 4 link(s), 20 image(s)
  * reason: E3: no date, and no source of the row places it outside the window: As the Pyramid of Love: an owner decision, not a date.
  * unified_sites.description: Excavations revealed only cracked sandstone plates separated by silt and clay layers -- consistent with natural geology, not construction.
  * pipeline/normalizers/dates.py:76-78: date = record.get('period_end') or record.get('period_start'); if date is None: return True  # No date = include (conservative)
  * snapshot:unified_sites: period_start = None, period_end = None, period_name = None
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:59 (1.3): The site is in scope (E3), or flagged as out of scope and hidden.
* **Bosnian Pyramid of the Sun** (`3c466fde-b751-4065-8de2-bd5c9280afe5`) - Bosnia and Herzegovina, Geological interest, period_start None, 4 link(s), 20 image(s)
  * reason: E3: no date, and no source of the row places it outside the window: As the Pyramid of Love: an owner decision. The only human structure the description names is the medieval royal fortress of Visoki.
  * unified_sites.description: Geologists identify it as a natural flatiron formation.
  * pipeline/normalizers/dates.py:76-78: date = record.get('period_end') or record.get('period_start'); if date is None: return True  # No date = include (conservative)
  * snapshot:unified_sites: period_start = None, period_end = None, period_name = None
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:59 (1.3): The site is in scope (E3), or flagged as out of scope and hidden.
* **Kamennyy Gorod** (`8459f1d2-a96f-4c37-a1d3-fb4ebbe3fb2e`) - Russia, Megalithic stones, period_start None, 5 link(s), 0 image(s)
  * reason: E3: no date, and no source of the row places it outside the window: No source_url and no date anywhere in the row: nothing places it outside the window.
  * unified_sites.description: A Megalithic site and protected nature reserve.
  * pipeline/normalizers/dates.py:76-78: date = record.get('period_end') or record.get('period_start'); if date is None: return True  # No date = include (conservative)
  * snapshot:unified_sites: period_start = None, period_end = None, period_name = None
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:59 (1.3): The site is in scope (E3), or flagged as out of scope and hidden.
* **Northern Avenue Petroglyph Site** (`fe9d2d34-c026-44cd-9883-86b23c96c962`) - USA, Petroglyphs, period_start None, 5 link(s), 0 image(s)
  * reason: E3: no date, and no source of the row places it outside the window: Its own source places it in prehistory, inside the Americas window: only the date field is missing.
  * unified_sites.description: the site served as a ceremonial site and animal facility in prehistory
  * pipeline/normalizers/dates.py:76-78: date = record.get('period_end') or record.get('period_start'); if date is None: return True  # No date = include (conservative)
  * snapshot:unified_sites: period_start = None, period_end = None, period_name = None
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:59 (1.3): The site is in scope (E3), or flagged as out of scope and hidden.
* **Prebreza** (`182f18fe-36ea-42c8-9a43-cbbc37d052a6`) - Serbia, City/town/settlement, period_start None, 5 link(s), 0 image(s)
  * reason: E3: no date, and no source of the row places it outside the window: A village with a Miocene paleontological site: a subject-scope question (not archaeology), not a date past the cutoff.
  * unified_sites.description: The Prebreza Paleontological site is regarded an important European Mammalian site of the Middle Miocene.
  * pipeline/normalizers/dates.py:76-78: date = record.get('period_end') or record.get('period_start'); if date is None: return True  # No date = include (conservative)
  * snapshot:unified_sites: period_start = None, period_end = None, period_name = None
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:59 (1.3): The site is in scope (E3), or flagged as out of scope and hidden.
* **Rocks of Saskatchewan** (`74c2c902-db56-411f-b98f-6711a6825b48`) - Canada, Geological interest, period_start None, 5 link(s), 0 image(s)
  * reason: E3: no date, and no source of the row places it outside the window: Nothing in the row dates it.
  * unified_sites.description: Very little is known about these rocks.
  * pipeline/normalizers/dates.py:76-78: date = record.get('period_end') or record.get('period_start'); if date is None: return True  # No date = include (conservative)
  * snapshot:unified_sites: period_start = None, period_end = None, period_name = None
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:59 (1.3): The site is in scope (E3), or flagged as out of scope and hidden.
* **Singing Stones of Brittany** (`045f1593-1dac-4504-9c53-ee8644a3134c`) - France, Geological interest, period_start None, 5 link(s), 11 image(s)
  * reason: E3: no date, and no source of the row places it outside the window: A natural phenomenon: a subject-scope question, not a date past the cutoff.
  * unified_sites.description: The phenomenon is due to the rock's mineral composition and density
  * pipeline/normalizers/dates.py:76-78: date = record.get('period_end') or record.get('period_start'); if date is None: return True  # No date = include (conservative)
  * snapshot:unified_sites: period_start = None, period_end = None, period_name = None
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:59 (1.3): The site is in scope (E3), or flagged as out of scope and hidden.
* **Situs Megalit Tebing Tinggi** (`cf3b581a-c47f-41c6-9922-48c6e3b8d3a0`) - Indonesia, Megalithic stones, period_start None, 4 link(s), 0 image(s)
  * reason: E3: no date, and no source of the row places it outside the window: Its own source places it inside the window: only the date field is missing.
  * unified_sites.description: Part of the Pasemah highlands megalithic tradition dating approximately 2,000-3,000 years ago
  * pipeline/normalizers/dates.py:76-78: date = record.get('period_end') or record.get('period_start'); if date is None: return True  # No date = include (conservative)
  * snapshot:unified_sites: period_start = None, period_end = None, period_name = None
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:59 (1.3): The site is in scope (E3), or flagged as out of scope and hidden.
* **Temple of Lemminkäinen** (`79898fb7-ea09-4366-93ee-d87e379e1aca`) - Finland, Cave Structures, period_start None, 3 link(s), 16 image(s)
  * reason: E3: no date, and no source of the row places it outside the window: The only date is the Bock saga's sealing of the cave, not its use; nothing places the site outside the window.
  * unified_sites.description: According to Bock, the entrance was sealed in 987 when Christianity arrived in Uusimaa
  * pipeline/normalizers/dates.py:76-78: date = record.get('period_end') or record.get('period_start'); if date is None: return True  # No date = include (conservative)
  * snapshot:unified_sites: period_start = None, period_end = None, period_name = None
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:59 (1.3): The site is in scope (E3), or flagged as out of scope and hidden.
* **Yonaguni Monument** (`01296632-a2a1-4610-a4a9-d0c3be77b788`) - Japan, Underwater structures, period_start None, 3 link(s), 20 image(s)
  * reason: E3: no date, and no source of the row places it outside the window: Natural or man-made is disputed and no source dates it: a subject-scope question.
  * unified_sites.description: Neither the Japanese Agency for Cultural Affairs nor Okinawa Prefecture recognises it as a cultural artifact.
  * pipeline/normalizers/dates.py:76-78: date = record.get('period_end') or record.get('period_start'); if date is None: return True  # No date = include (conservative)
  * snapshot:unified_sites: period_start = None, period_end = None, period_name = None
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:59 (1.3): The site is in scope (E3), or flagged as out of scope and hidden.

## (c) true duplicates - 19 site(s)

### retired (19)

* **Ancient Kourion** (`d120ca9a-703b-49e2-b333-ad6dfe508953`) - Cyprus, City/town/settlement, period_start -1050, 4 link(s), 20 image(s)
  * reason: duplicate_of:9983bdce-9f35-47a3-a570-4021cfa41b97
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q1785592, 469.4 m apart
  * production:site_external_ids: both rows carry Q1785592; 'Ancient Kourion' and 'Kourion' are both names of it (labels, aliases or sitelinks); 469.4 m apart
  * survivor rule: 'Kourion' survives by more content links: content links 5 vs 4, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 20 wiki_images and 4 content links that are not moved by retiring it; country 'Cyprus' vs survivor 'Cyprus'
* **Archaeological Park Carnuntum** (`f3da4b6e-c4a3-4416-9c28-93bf761119ad`) - Austria, Fortress/citadel, period_start 1, 3 link(s), 20 image(s)
  * reason: duplicate_of:1531d4a1-bb24-4727-9b25-f2089088acaf
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q508815, 9.1 m apart
  * production:site_external_ids: both rows carry Q508815; 'Archaeological Park Carnuntum' and 'Carnuntum' are both names of it (labels, aliases or sitelinks); 9.1 m apart
  * survivor rule: 'Carnuntum' survives by more content links: content links 5 vs 3, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 20 wiki_images and 3 content links that are not moved by retiring it; country 'Austria' vs survivor 'Austria'
* **Archaeological Site of Kition** (`55a670ec-c7c5-4f52-98ea-b25211aedd4e`) - Cyprus, City/town/settlement, period_start -3000, 4 link(s), 17 image(s)
  * reason: duplicate_of:47c37ef9-98ee-41d8-879b-e78db06295da
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q1743884, 62.9 m apart
  * production:site_external_ids: both rows carry Q1743884; 'Archaeological Site of Kition' and 'Kition' are both names of it (labels, aliases or sitelinks); 62.9 m apart
  * survivor rule: 'Kition' survives by more content links: content links 5 vs 4, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 17 wiki_images and 4 content links that are not moved by retiring it; country 'Cyprus' vs survivor 'Cyprus'
* **Archaeological Site, Heraion** (`24676ed3-9308-42d4-bf35-1c739f0652e2`) - Greece, Temple complex, period_start -1500, 4 link(s), 20 image(s)
  * reason: duplicate_of:9d9d94a0-f338-4392-860f-983c29fabb16
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q2070087, 122.1 m apart
  * production:site_external_ids: both rows carry Q2070087; 'Archaeological Site, Heraion' and 'Heraion of Perachora' are both names of it (labels, aliases or sitelinks); 122.1 m apart
  * survivor rule: 'Heraion of Perachora' survives by more content links: content links 5 vs 4, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 20 wiki_images and 4 content links that are not moved by retiring it; country 'Greece' vs survivor 'Greece'
* **Area Archeologica di Alba Fucens** (`13c3f25f-3887-49c1-9492-cf7e512e5782`) - Italy, City, period_start -303, 5 link(s), 0 image(s)
  * reason: duplicate_of:13120650-2e61-45af-976c-b2e0665c49af
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q944515, 89.1 m apart
  * production:site_external_ids: both rows carry Q944515; 'Area Archeologica di Alba Fucens' and 'Alba Fucens' are both names of it (labels, aliases or sitelinks); 89.1 m apart
  * survivor rule: 'Alba Fucens' survives by lower id (tie-break): content links 5 vs 5, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 0 wiki_images and 5 content links that are not moved by retiring it; country 'Italy' vs survivor 'Italy'
* **Augusta Bilbilis** (`577b13cd-242b-4951-a8c4-ab3ecde0e5b1`) - Spain, City/town/settlement, period_start -500, 4 link(s), 8 image(s)
  * reason: duplicate_of:23576019-c749-4ee9-95b1-cdae21f5ff06
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q860500, 102.5 m apart
  * production:site_external_ids: both rows carry Q860500; 'Augusta Bilbilis' and 'Bilbilis' are both names of it (labels, aliases or sitelinks); 102.5 m apart
  * survivor rule: 'Bilbilis' survives by more content links: content links 5 vs 4, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 8 wiki_images and 4 content links that are not moved by retiring it; country 'Spain' vs survivor 'Spain'
* **Bishop's Basilica of Philippopolis** (`b46b6969-3160-4cbd-a574-8727ee7c53c5`) - Bulgaria, Temple complex, period_start 1, 3 link(s), 20 image(s)
  * reason: duplicate_of:891ad351-7985-4c16-b6a6-830c26bc268f
  * wikidata:Q20500169: both 'Great Basilica, Plovdiv' and "Bishop's Basilica of Philippopolis" are names of Q20500169, and the two rows are 6.2 m apart
  * survivor rule: older row, then more content links, description citations, images: survivor Great Basilica, Plovdiv (5 links, 1 citations, 20 images) over Bishop's Basilica of Philippopolis (3 links, 0 citations, 20 images)
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q20500169, 6.2 m apart
  * production:site_external_ids: both rows carry Q20500169; "Bishop's Basilica of Philippopolis" and 'Great Basilica, Plovdiv' are both names of it (labels, aliases or sitelinks); 6.2 m apart
  * survivor rule: 'Great Basilica, Plovdiv' survives by more content links: content links 5 vs 3, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 20 wiki_images and 3 content links that are not moved by retiring it; country 'Bulgaria' vs survivor 'Bulgaria'
* **Ciudad Romana de Cáparra** (`cf49332c-0a05-4ba7-bf4f-48a703ee7a1e`) - Spain, Gate/archway/bridge, period_start 1, 0 link(s), 0 image(s)
  * reason: duplicate_of:577f2ec4-3dc0-4d10-9425-39f1cb654009
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q2580972, 343.1 m apart
  * production:site_external_ids: both rows carry Q2580972; 'Ciudad Romana de Cáparra' and 'Cáparra' are both names of it (labels, aliases or sitelinks); 343.1 m apart
  * survivor rule: 'Cáparra' survives by more content links: content links 4 vs 0, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 0 wiki_images and 0 content links that are not moved by retiring it; country 'Spain' vs survivor 'Spain'
* **Coricancha** (`4e6247b0-7416-413f-b7a3-b31890a45f3b`) - Peru, Temple complex, period_start 1000, 0 link(s), 20 image(s)
  * reason: duplicate_of:4a9b3802-1067-4f6b-a144-4c2ffe9619a4
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q817594, 100.6 m apart
  * production:site_external_ids: both rows carry Q817594; 'Coricancha' and 'Qorikancha' are both names of it (labels, aliases or sitelinks); 100.6 m apart
  * survivor rule: 'Qorikancha' survives by lower id (tie-break): content links 0 vs 0, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 20 wiki_images and 0 content links that are not moved by retiring it; country 'Peru' vs survivor 'Peru'
* **Dodona** (`5a04d6f3-c82d-4c82-b1e9-3d70bff135ae`) - Greece, Temple complex, period_start -2000, 5 link(s), 20 image(s)
  * reason: duplicate_of:56f594fc-6819-4d51-98a4-1cf5b4a265a6
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q382317, 250.1 m apart
  * production:site_external_ids: both rows carry Q382317; 'Dodona' and 'Archaeological Site of Dodoni' are both names of it (labels, aliases or sitelinks); 250.1 m apart
  * survivor rule: 'Archaeological Site of Dodoni' survives by lower id (tie-break): content links 5 vs 5, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 20 wiki_images and 5 content links that are not moved by retiring it; country 'Greece' vs survivor 'Greece'
* **Dolmen of Menga** (`ab03fa75-bbdc-46a2-ba55-25e2f5edd5c4`) - Spain, Dolmen, period_start -4000, 0 link(s), 20 image(s)
  * reason: duplicate_of:485c3c0c-31f0-45a7-a06b-797c4c021466
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q1143218, 178.9 m apart
  * production:site_external_ids: both rows carry Q1143218; 'Dolmen of Menga' and 'Dolmen de Menga' are both names of it (labels, aliases or sitelinks); 178.9 m apart
  * survivor rule: 'Dolmen de Menga' survives by more content links: content links 5 vs 0, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 20 wiki_images and 0 content links that are not moved by retiring it; country 'Spain' vs survivor 'Spain'
* **Dooey's Cairn** (`f5ca382a-3725-4cbb-961a-6afbf5c21507`) - Northern Ireland, Cairn, period_start -4500, 0 link(s), 3 image(s)
  * reason: duplicate_of:f6b6e039-36f1-4107-b730-dc2aa34b7a92
  * wikidata:Q1242421: both 'Ballymacaldrack Court Tomb' and "Dooey's Cairn" are names of Q1242421, and the two rows are 7.1 m apart
  * survivor rule: older row, then more content links, description citations, images: survivor Ballymacaldrack Court Tomb (5 links, 3 citations, 3 images) over Dooey's Cairn (0 links, 2 citations, 3 images)
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q1242421, 7.1 m apart
  * production:site_external_ids: both rows carry Q1242421; "Dooey's Cairn" and 'Ballymacaldrack Court Tomb' are both names of it (labels, aliases or sitelinks); 7.0 m apart
  * survivor rule: 'Ballymacaldrack Court Tomb' survives by more content links: content links 5 vs 0, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 3 wiki_images and 0 content links that are not moved by retiring it; country 'Northern Ireland' vs survivor 'Northern Ireland'
* **Hattuşa Örenyeri** (`7e33b1ac-bb32-4b6c-b070-2c4fdcaf19fb`) - Türkiye, Megalithic stones, period_start -2000, 0 link(s), 20 image(s)
  * reason: duplicate_of:109fcdea-c114-4143-87ac-77c4c9c20f16
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q181007, 1216.4 m apart
  * production:site_external_ids: both rows carry Q181007; 'Hattuşa Örenyeri' and 'Hattusas' are both names of it (labels, aliases or sitelinks); 1216.4 m apart
  * survivor rule: 'Hattusas' survives by lower id (tie-break): content links 0 vs 0, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 20 wiki_images and 0 content links that are not moved by retiring it; country 'Türkiye' vs survivor 'Türkiye'
* **Olympos Ruins** (`04d8ce82-4fa3-4e48-88b7-bb41b354260c`) - Türkiye, City/town/settlement, period_start -1500, 0 link(s), 20 image(s)
  * reason: duplicate_of:00f522ff-8e1b-4983-961c-ef6cb1ff27d1
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q1380189, 111.8 m apart
  * production:site_external_ids: both rows carry Q1380189; 'Olympos Ruins' and 'Olympos Antique City' are both names of it (labels, aliases or sitelinks); 111.8 m apart
  * survivor rule: 'Olympos Antique City' survives by lower id (tie-break): content links 0 vs 0, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 20 wiki_images and 0 content links that are not moved by retiring it; country 'Türkiye' vs survivor 'Türkiye'
* **Pinara Antique City** (`8cecb38f-08cf-4a93-b350-9ccbb74109bb`) - Türkiye, Necropolis/tombs complex, period_start -3000, 5 link(s), 20 image(s)
  * reason: duplicate_of:5025eee3-28ea-46d6-b2c3-dbb1f38a24d6
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q1318876, 38.9 m apart
  * production:site_external_ids: both rows carry Q1318876; 'Pinara Antique City' and 'Pinara' are both names of it (labels, aliases or sitelinks); 38.9 m apart
  * survivor rule: 'Pinara' survives by lower id (tie-break): content links 5 vs 5, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 20 wiki_images and 5 content links that are not moved by retiring it; country 'Türkiye' vs survivor 'Türkiye'
* **Tarxien Temples** (`4a5a324f-832f-4dca-b688-d4a006d297c7`) - Malta, Temple complex, period_start -4500, 0 link(s), 20 image(s)
  * reason: duplicate_of:318414bc-098b-4459-95c0-41e1ec49c8a8
  * wikidata:Q1064331: both 'Templos de Tarxien' and 'Tarxien Temples' are names of Q1064331, and the two rows are 38.2 m apart
  * survivor rule: older row, then more content links, description citations, images: survivor Templos de Tarxien (5 links, 0 citations, 0 images) over Tarxien Temples (0 links, 0 citations, 20 images)
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q1064331, 38.2 m apart
  * production:site_external_ids: both rows carry Q1064331; 'Tarxien Temples' and 'Templos de Tarxien' are both names of it (labels, aliases or sitelinks); 38.2 m apart
  * survivor rule: 'Templos de Tarxien' survives by more content links: content links 5 vs 0, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 20 wiki_images and 0 content links that are not moved by retiring it; country 'Malta' vs survivor 'Malta'
* **Templo Romano Évora** (`07fb4e2f-26e5-4720-a949-9c28d4712e11`) - Portugal, Temple complex, period_start 1, 0 link(s), 20 image(s)
  * reason: duplicate_of:9152beea-f7ab-40ef-a692-ef63ac8e9ca6
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q737441, 51.8 m apart
  * production:site_external_ids: both rows carry Q737441; 'Templo Romano Évora' and 'Roman Temple of Évora' are both names of it (labels, aliases or sitelinks); 51.8 m apart
  * survivor rule: 'Roman Temple of Évora' survives by more content links: content links 5 vs 0, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 20 wiki_images and 0 content links that are not moved by retiring it; country 'Portugal' vs survivor 'Portugal'
* **Termantia** (`93391ee6-8e80-42db-922c-11f64ea57db9`) - Spain, Fortress/citadel, period_start -500, 5 link(s), 20 image(s)
  * reason: duplicate_of:84ef64f3-394a-4b35-ba4a-7e81b3b6a317
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q2429023, 162.7 m apart
  * production:site_external_ids: both rows carry Q2429023; 'Termantia' and 'Tiermes Archaeological Site' are both names of it (labels, aliases or sitelinks); 162.7 m apart
  * survivor rule: 'Tiermes Archaeological Site' survives by lower id (tie-break): content links 5 vs 5, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 20 wiki_images and 5 content links that are not moved by retiring it; country 'Spain' vs survivor 'Spain'
* **The Aqueduct of Jerwan** (`4687a49a-c987-4c56-bc6e-5094aa57667d`) - Iraq, Megalithic structures, period_start -1500, 0 link(s), 20 image(s)
  * reason: duplicate_of:c6d9487d-d138-4d73-beb1-5735e50da048
  * bcases:DUPLICATES.jsonl: listed for the scope lane; re-read in the export: both rows carry Q17064815, 5.5 m apart
  * production:site_external_ids: both rows carry Q17064815; 'The Aqueduct of Jerwan' and 'Jerwan' are both names of it (labels, aliases or sitelinks); 5.5 m apart
  * survivor rule: 'Jerwan' survives by more content links: content links 5 vs 0, sources 2+url vs 2+url, created 2026-03-04 21:07:57.660461 vs 2026-03-04 21:07:57.660461
  * follow-up: the loser carries 20 wiki_images and 0 content links that are not moved by retiring it; country 'Iraq' vs survivor 'Iraq'

## (d) Museum rows (plan section 8.2) - 20 site(s)

### retired (3)

* **Groß Raden Archaeological Open Air Museum** (`9bbea428-26aa-4cb9-a9c8-d3f8f059972d`) - Germany, Museum, period_start 800, 5 link(s), 20 image(s)
  * reason: E3 museum rule (plan section 8.2): Plan section 8.2: one of the 3 Museum rows that leave (Slavic settlement and temple, 9th/10th century). Phase 3 wrote period_start 1 -> 800.
  * unified_sites.description: uncovered remains of a Slavic settlement dating to the 9th and 10th centuries
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 11.87806632619278, date = 800]
  * snapshot:unified_sites.period_start: period_start = 800, period_end = None, period_name = '500 - 1000 AD', lat = 53.73671109492367, lon = 11.87806632619278
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Germany; CONTINENT = Europe; region from the longitude window: rest of world (Natural Earth: Europe)
  * remediation_change_log:28661: phase3:batch-0176:chunk-0001: period_start 1 -> 800
* **Khushuu Tsaidam Museum** (`71d8e2bc-7406-4c4a-b68d-2ff1b71800e8`) - Mongolia, Museum, period_start 2008, 5 link(s), 1 image(s)
  * reason: E3 museum rule (plan section 8.2): Plan section 8.2: one of the 3 Museum rows that leave (Gokturk Orkhon stelae, 8th century).
  * unified_sites.description: dedicated to the 8th-century Orkhon inscriptions of the Gokturk Empire
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 102.87002330462411, date = 2008]
  * snapshot:unified_sites.period_start: period_start = 2008, period_end = None, period_name = '1500+ AD', lat = 47.5668027716464, lon = 102.87002330462411
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Mongolia; CONTINENT = Asia; region from the longitude window: rest of world (Natural Earth: Asia)
* **King Richard III Visitor Centre** (`aa56465b-1a9e-45b2-abec-b50be3796d8f`) - England, Museum, period_start 2014, 5 link(s), 15 image(s)
  * reason: E3 museum rule (plan section 8.2): Plan section 8.2: one of the 3 Museum rows that leave (the 1485 grave of Richard III).
  * unified_sites.description: where Richard III was buried in 1485
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = -1.1361785450390818, date = 2014]
  * snapshot:unified_sites.period_start: period_start = 2014, period_end = None, period_name = '1500+ AD', lat = 52.634330198838356, lon = -1.1361785450390818
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: United Kingdom; CONTINENT = Europe; region from the longitude window: rest of world (Natural Earth: Europe)

### in_scope (17)

* **Delphi Archaeological Museum** (`660f8d4f-9fbd-43ea-8431-18c9327e81ea`) - Greece, Museum, period_start 1903, 0 link(s), 20 image(s)
  * reason: E3 museum rule (plan section 8.2): E3 museum rule: exhibits ancient material; period_start 1903 is the founding year.
  * unified_sites.description: The collection spans from the Late Helladic (Mycenean) period to the early Byzantine era
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 22.499908838843965, date = 1903]
  * snapshot:unified_sites.period_start: period_start = 1903, period_end = None, period_name = '1500+ AD', lat = 38.48036263756499, lon = 22.499908838843965
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Greece; CONTINENT = Europe; region from the longitude window: rest of world (Natural Earth: Europe)
* **Ephesus Archaeological Museum** (`7ca988d4-73af-4ed2-b4ab-d93d080aa486`) - Türkiye, Museum, period_start 1964, 5 link(s), 20 image(s)
  * reason: E3 museum rule (plan section 8.2): E3 museum rule: exhibits ancient material; period_start 1964 is the founding year.
  * unified_sites.description: Its most celebrated exhibit is the ancient statue of the Greek Goddess Artemis
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 27.368058402498587, date = 1964]
  * snapshot:unified_sites.period_start: period_start = 1964, period_end = None, period_name = '1500+ AD', lat = 37.94908898562895, lon = 27.368058402498587
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Turkey; CONTINENT = Asia; region from the longitude window: rest of world (Natural Earth: Asia)
* **Grenoble Archaeological Museum** (`52bd1b99-5377-4a93-903d-cf99738b9926`) - France, Museum, period_start 1846, 5 link(s), 20 image(s)
  * reason: E3 museum rule (plan section 8.2): E3 museum rule: exhibits ancient material; period_start 1846 is not the date of the collection.
  * unified_sites.description: The site preserves layers from a 4th-century Gallo-Roman necropolis
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 5.731389268023541, date = 1846]
  * snapshot:unified_sites.period_start: period_start = 1846, period_end = None, period_name = '1500+ AD', lat = 45.19788141583053, lon = 5.731389268023541
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: France; CONTINENT = Europe; region from the longitude window: rest of world (Natural Earth: Europe)
* **Jadar Museum** (`e93e16aa-f555-4ad7-8ede-d8120fdf29a1`) - Serbia, Museum, period_start 1984, 5 link(s), 16 image(s)
  * reason: E3 museum rule (plan section 8.2): E3 museum rule: exhibits ancient material; period_start 1984 is not the date of the collection.
  * unified_sites.description: Notable exhibits include Roman-era Illyrian artifacts
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 19.2246939986745, date = 1984]
  * snapshot:unified_sites.period_start: period_start = 1984, period_end = None, period_name = '1500+ AD', lat = 44.53179462751145, lon = 19.2246939986745
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Republic of Serbia; CONTINENT = Europe; region from the longitude window: rest of world (Natural Earth: Europe)
* **Kharakhorum Museum** (`ff1c4702-9115-43fc-b64f-15a9729bc6d9`) - Mongolia, Museum, period_start 2007, 5 link(s), 20 image(s)
  * reason: E3 museum rule (plan section 8.2): E3 museum rule: exhibits ancient material; period_start 2007 is the building's start.
  * unified_sites.description: It houses 3,128 artifacts spanning from the Upper Palaeolithic to the 14th century
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 102.85477346391565, date = 2007]
  * snapshot:unified_sites.period_start: period_start = 2007, period_end = None, period_name = '1500+ AD', lat = 47.19923322204278, lon = 102.85477346391565
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Mongolia; CONTINENT = Asia; region from the longitude window: rest of world (Natural Earth: Asia)
* **Leptis Magna Museum** (`f1ec1e6c-f23c-40a9-ac6e-293965a8bd60`) - Libya, Museum, period_start None, 5 link(s), 0 image(s)
  * reason: E3 museum rule (plan section 8.2): Undated Museum row: the E3 museum rule keeps it - it exhibits ancient material.
  * unified_sites.description: It contains evidence of people of different origins that once inhabited the city of Leptis Magna, including Berber, Punic, Phoenicians and Romans.
  * pipeline/normalizers/dates.py:76-78: date = record.get('period_end') or record.get('period_start'); if date is None: return True  # No date = include (conservative)
  * snapshot:unified_sites: period_start = None, period_end = None, period_name = None
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:59 (1.3): The site is in scope (E3), or flagged as out of scope and hidden.
* **Maria Reiche Museum** (`5ed144bd-59e1-4611-a462-a3098bea5231`) - Peru, Museum, period_start 1994, 5 link(s), 0 image(s)
  * reason: E3 museum rule (plan section 8.2): E3 museum rule: the museum of the Nazca Lines research displays archaeological finds; period_start 1994 is not the date of the collection.
  * unified_sites.description: the house was converted into a museum displaying her research materials, maps, blueprints, and archaeological finds
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 1500 (Americas); return date <= cutoff   [lon = -75.13680700162324, date = 1994]
  * snapshot:unified_sites.period_start: period_start = 1994, period_end = None, period_name = '1500+ AD', lat = -14.68158327621296, lon = -75.13680700162324
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Peru; CONTINENT = South America; region from the longitude window: Americas (Natural Earth: South America)
* **Museo Campano** (`3bcf804a-ff18-4066-89bd-cfaa8a3b5a46`) - Italy, Museum, period_start 1869, 5 link(s), 20 image(s)
  * reason: E3 museum rule (plan section 8.2): E3 museum rule: exhibits ancient material; period_start 1869 is the founding year.
  * unified_sites.description: houses an extensive collection of matres matutae ritual statues from the ancient Roman site of Capua antica
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 14.213266798496122, date = 1869]
  * snapshot:unified_sites.period_start: period_start = 1869, period_end = None, period_name = '1500+ AD', lat = 41.111076842523865, lon = 14.213266798496122
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Italy; CONTINENT = Europe; region from the longitude window: rest of world (Natural Earth: Europe)
* **Museo Nacional de Antropología** (`7b061e76-f20f-447d-9650-c334492b86dc`) - Mexico, Museum, period_start 1964, 5 link(s), 20 image(s)
  * reason: E3 museum rule (plan section 8.2): E3 museum rule: exhibits ancient material; period_start 1964 is the inauguration year.
  * unified_sites.description: The museum houses eleven anthropology galleries covering pre-Columbian civilizations including Teotihuacan
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 1500 (Americas); return date <= cutoff   [lon = -99.18606818884527, date = 1964]
  * snapshot:unified_sites.period_start: period_start = 1964, period_end = None, period_name = '1500+ AD', lat = 19.426323560887933, lon = -99.18606818884527
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Mexico; CONTINENT = North America; region from the longitude window: Americas (Natural Earth: North America)
* **Museo Regional de Antropologia Carlos Pellier** (`c1e49d01-2e46-4ecc-af7f-1fd39555fc8e`) - Mexico, Museum, period_start 1980, 5 link(s), 0 image(s)
  * reason: E3 museum rule (plan section 8.2): E3 museum rule: exhibits ancient material; period_start 1980 is the opening year.
  * unified_sites.description: The collection includes monumental Olmec stone sculptures from La Venta
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 1500 (Americas); return date <= cutoff   [lon = -92.97200344470167, date = 1980]
  * snapshot:unified_sites.period_start: period_start = 1980, period_end = None, period_name = '1500+ AD', lat = 17.974104087667964, lon = -92.97200344470167
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Mexico; CONTINENT = North America; region from the longitude window: Americas (Natural Earth: North America)
* **Museo Regional de Campeche** (`d48eb704-d535-4be7-9695-868ee650cbb7`) - Mexico, Museum, period_start 1986, 0 link(s), 0 image(s)
  * reason: E3 museum rule (plan section 8.2): E3 museum rule: exhibits ancient material; period_start 1986 is the opening year.
  * unified_sites.description: This two-story building displays a pre-Hispanic collection from the Gulf and Central Highlands regions
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 1500 (Americas); return date <= cutoff   [lon = -90.56875510602956, date = 1986]
  * snapshot:unified_sites.period_start: period_start = 1986, period_end = None, period_name = '1500+ AD', lat = 19.82486156224875, lon = -90.56875510602956
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Mexico; CONTINENT = North America; region from the longitude window: Americas (Natural Earth: North America)
* **Museo de Antropologia de Xalapa** (`761dfa49-30a6-4e09-a4c6-cb5294f3a98e`) - Mexico, Museum, period_start 1937, 5 link(s), 7 image(s)
  * reason: E3 museum rule (plan section 8.2): E3 museum rule: exhibits ancient material; period_start 1937 is the founding year.
  * unified_sites.description: The museum houses artifacts from Mesoamerican Gulf Coast cultures including the Olmec, Totonac, and Huastec
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 1500 (Americas); return date <= cutoff   [lon = -96.93110027534972, date = 1937]
  * snapshot:unified_sites.period_start: period_start = 1937, period_end = None, period_name = '1500+ AD', lat = 19.550798628335173, lon = -96.93110027534972
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Mexico; CONTINENT = North America; region from the longitude window: Americas (Natural Earth: North America)
* **Museo de la Arquitectura Maya** (`9108b193-4370-4997-a271-7d20836efeed`) - Mexico, Museum, period_start 2005, 5 link(s), 0 image(s)
  * reason: E3 museum rule (plan section 8.2): E3 museum rule: exhibits ancient material; period_start 2005 is the reopening year.
  * unified_sites.description: The collection showcases architectural elements from four regional Maya styles
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 1500 (Americas); return date <= cutoff   [lon = -90.53777563116269, date = 2005]
  * snapshot:unified_sites.period_start: period_start = 2005, period_end = None, period_name = '1500+ AD', lat = 19.846491722096893, lon = -90.53777563116269
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Mexico; CONTINENT = North America; region from the longitude window: Americas (Natural Earth: North America)
* **Mérida Anthropological Museum** (`01c36727-31bd-45ae-9908-5c7043403cd2`) - Mexico, Museum, period_start 1959, 5 link(s), 0 image(s)
  * reason: E3 museum rule (plan section 8.2): E3 museum rule: exhibits ancient material; period_start 1959 is not the date of the collection.
  * unified_sites.description: The permanent collection spans from the pre-Classic to the late post-Classic Maya period
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 1500 (Americas); return date <= cutoff   [lon = -89.61956437716287, date = 1959]
  * snapshot:unified_sites.period_start: period_start = 1959, period_end = None, period_name = '1500+ AD', lat = 20.97808029939197, lon = -89.61956437716287
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Mexico; CONTINENT = North America; region from the longitude window: Americas (Natural Earth: North America)
* **Pfahlbaumuseum Unteruhldingen** (`ef91e19e-db13-4475-b6a8-feb6f3298146`) - Germany, Museum, period_start 1922, 5 link(s), 20 image(s)
  * reason: E3 museum rule (plan section 8.2): E3 museum rule: exhibits (reconstructed) ancient material; period_start 1922 is the founding year.
  * unified_sites.description: featuring reconstructions of Neolithic and Bronze Age stilt houses
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = 9.227734881656517, date = 1922]
  * snapshot:unified_sites.period_start: period_start = 1922, period_end = None, period_name = '1500+ AD', lat = 47.72612550524633, lon = 9.227734881656517
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: Germany; CONTINENT = Europe; region from the longitude window: rest of world (Natural Earth: Europe)
* **The Davidson Center** (`bcfba32b-fa88-44a0-8dc9-ace3a9416bb9`) - Israel, Museum, period_start None, 5 link(s), 0 image(s)
  * reason: E3 museum rule (plan section 8.2): Undated Museum row: the E3 museum rule keeps it - it exhibits ancient material.
  * unified_sites.description: The site spans approximately 5,000 years of history from the Canaanite Bronze Age through the Second Temple period.
  * pipeline/normalizers/dates.py:76-78: date = record.get('period_end') or record.get('period_start'); if date is None: return True  # No date = include (conservative)
  * snapshot:unified_sites: period_start = None, period_end = None, period_name = None
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:59 (1.3): The site is in scope (E3), or flagged as out of scope and hidden.
* **The Salisbury Museum** (`18253743-256d-497f-be7b-6a7400d33593`) - England, Museum, period_start 1860, 3 link(s), 20 image(s)
  * reason: E3 museum rule (plan section 8.2): E3 museum rule: exhibits ancient material; period_start 1860 is the founding year.
  * unified_sites.description: including prehistoric material from Stonehenge
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:46 (E3): Museums stay if they exhibit ancient material. Cutoff: Americas through 1500 AD, rest of world through 500 AD.
  * docs/procedures/SITES_DB_REMEDIATION_2026-09.md:430 (8.2): - **41 stay** — they exhibit ancient material
  * pipeline/normalizers/dates.py:85-88 (passes_date_cutoff): is_americas = -170 <= lon <= -30; cutoff = 500 (rest of world); return date <= cutoff   [lon = -1.8001214604772753, date = 1860]
  * snapshot:unified_sites.period_start: period_start = 1860, period_end = None, period_name = '1500+ AD', lat = 51.06468876090109, lon = -1.8001214604772753
  * naturalearth:ne_10m_admin_0_countries (CONTINENT): contains the point: United Kingdom; CONTINENT = Europe; region from the longitude window: rest of world (Natural Earth: Europe)

## Pairs within 100 m that share a Wikidata item but are not duplicates (94)

At least one of the two names is not a name of the shared item: a sub-site, a part-of pair or a wrong anchor - never retired here.

* Q10751359: Temple of Apollo, Delphi / Apollo Temple, Delphi (90.1 m; names known: False/False)
* Q12065255: Early Roman House / House of Aion (88.6 m; names known: False/False)
* Q12065255: Hellenistic House / Villa of Theseus (51.3 m; names known: False/False)
* Q12065255: Hellenistic House / House of Orpheus (76.0 m; names known: False/False)
* Q12065255: Hellenistic House / Early Roman House (43.0 m; names known: False/False)
* Q12065255: Paphos Archaeological Park / Hellenistic House (76.5 m; names known: True/False)
* Q12065255: Paphos Archaeological Park / Early Roman House (74.8 m; names known: True/False)
* Q12065255: Villa of Theseus / House of Orpheus (81.6 m; names known: False/False)
* Q12065255: Villa of Theseus / Early Roman House (55.0 m; names known: False/False)
* Q12065255: Villa of Theseus / House of Aion (79.0 m; names known: False/False)
* Q12630293: Porta Gemina / Twin Gates of Pula (29.6 m; names known: True/False)
* Q1318876: Pinara / Pinara Antique City (39.0 m; names known: True/False)
* Q134140: Abu Simbel Temples / Temple of Ramesses II- Abu Simbel (74.6 m; names known: True/False)
* Q134140: Abu Simbel Temples / Temple of Nefertari- Abu Simbel (55.5 m; names known: True/False)
* Q1568283: Milecastles - Hadrian's Wall / Milefortlet - Hadrians Wall (0.0 m; names known: False/False)
* Q17064815: The Aqueduct of Jerwan / Jerwan (5.5 m; names known: False/True)
* Q17074808: Killarumiyoq / Killarumiyuq (91.5 m; names known: False/True)
* Q173527: Knossos / Minoan Palace of Knossos (78.6 m; names known: True/False)
* Q1743884: Kition / Archaeological Site of Kition (62.7 m; names known: True/False)
* Q1796353: Archaeological Site of the Tombs of the Kings / Tombs of the Kings, Paphos (25.0 m; names known: False/False)
* Q188694: Butrint / Butrint Ancient Theatre (14.3 m; names known: True/False)
* Q2061016: Banna, Birdoswald / Birdoswald Roman Fort (2.2 m; names known: False/True)
* Q2343313: Ancient Amathunta / Amathus (11.2 m; names known: False/True)
* Q27987850: Biniai Nou Hypogea / Hipogeo de Biniai nou (16.5 m; names known: True/False)
* Q3157009: Roman Temple of Hercules / Amman Citadel (50.1 m; names known: False/True)
* Q4636108: Bridge Street Number 39, Chester / Thirty-nine (39) Bridge Street, Chester (14.1 m; names known: False/False)
* Q475497: Sanctuary of Artemis, Brauron / Brauron (6.6 m; names known: False/True)
* Q502897: Mycenaean Acropolis of Midea / Midea, Argolid (11.7 m; names known: False/False)
* Q508815: Carnuntum / Archaeological Park Carnuntum (9.1 m; names known: True/False)
* Q5276996: Dilmun Burial Mounds - Dar Kulaib Burial Mound Field / Dilmun Burial Mounds - A'ali West Burial Mound Field (99.9 m; names known: False/False)
* Q5289390: Dolmen del prado de Lácara / Dolmen de Lácara (38.1 m; names known: True/False)
* Q5584221: Bruach An Druimein, Kimartin Glen / Glebe Cairn, Kilmartin Glen (4.5 m; names known: False/False)
* Q5584221: Bruach An Druimein, Kimartin Glen / Ri Cruin Cairn, Kilmartin Glen (4.3 m; names known: False/False)
* Q5584221: Bruach An Druimein, Kimartin Glen / The Linear Cemetery, Kilmartin Glen (4.8 m; names known: False/False)
* Q5584221: Bruach An Druimein, Kimartin Glen / Cup and Ring marks, Kilmartin Glen (4.5 m; names known: False/False)
* Q5584221: Bruach An Druimein, Kimartin Glen / Nether Largie Mid Cairn, Kilmartin Glen (4.3 m; names known: False/False)
* Q5584221: Carving depicting Animals, Kilmartin Glen / Nether Largie Standing Stones, Kilmartin Glen (6.8 m; names known: False/False)
* Q5584221: Carving depicting Animals, Kilmartin Glen / Bruach An Druimein, Kimartin Glen (9.6 m; names known: False/False)
* Q5584221: Carving depicting Animals, Kilmartin Glen / Glebe Cairn, Kilmartin Glen (5.3 m; names known: False/False)
* Q5584221: Carving depicting Animals, Kilmartin Glen / Ri Cruin Cairn, Kilmartin Glen (6.8 m; names known: False/False)
* Q5584221: Carving depicting Animals, Kilmartin Glen / The Linear Cemetery, Kilmartin Glen (8.4 m; names known: False/False)
* Q5584221: Carving depicting Animals, Kilmartin Glen / Cup and Ring marks, Kilmartin Glen (5.3 m; names known: False/False)
* Q5584221: Carving depicting Animals, Kilmartin Glen / Nether Largie Mid Cairn, Kilmartin Glen (6.8 m; names known: False/False)
* Q5584221: Cup and Ring marks, Kilmartin Glen / Nether Largie Mid Cairn, Kilmartin Glen (1.9 m; names known: False/False)
* Q5584221: Glebe Cairn, Kilmartin Glen / Ri Cruin Cairn, Kilmartin Glen (1.9 m; names known: False/False)
* Q5584221: Glebe Cairn, Kilmartin Glen / The Linear Cemetery, Kilmartin Glen (3.8 m; names known: False/False)
* Q5584221: Glebe Cairn, Kilmartin Glen / Cup and Ring marks, Kilmartin Glen (0.0 m; names known: False/False)
* Q5584221: Glebe Cairn, Kilmartin Glen / Nether Largie Mid Cairn, Kilmartin Glen (1.9 m; names known: False/False)
* Q5584221: Kilmartin Glen / Nether Largie South Cairn, Kilmartin Glen (1.9 m; names known: True/False)
* Q5584221: Kilmartin Glen / Nether Largie North Cairn, Kilmartin Glen (1.9 m; names known: True/False)
* Q5584221: Kilmartin Glen / Carving depicting Animals, Kilmartin Glen (5.3 m; names known: True/False)
* Q5584221: Kilmartin Glen / Nether Largie Standing Stones, Kilmartin Glen (1.9 m; names known: True/False)
* Q5584221: Kilmartin Glen / Bruach An Druimein, Kimartin Glen (4.5 m; names known: True/False)
* Q5584221: Kilmartin Glen / Glebe Cairn, Kilmartin Glen (0.0 m; names known: True/False)
* Q5584221: Kilmartin Glen / Ri Cruin Cairn, Kilmartin Glen (1.9 m; names known: True/False)
* Q5584221: Kilmartin Glen / The Linear Cemetery, Kilmartin Glen (3.8 m; names known: True/False)
* Q5584221: Kilmartin Glen / Cup and Ring marks, Kilmartin Glen (0.0 m; names known: True/False)
* Q5584221: Kilmartin Glen / Nether Largie Mid Cairn, Kilmartin Glen (1.9 m; names known: True/False)
* Q5584221: Nether Largie North Cairn, Kilmartin Glen / Carving depicting Animals, Kilmartin Glen (6.8 m; names known: False/False)
* Q5584221: Nether Largie North Cairn, Kilmartin Glen / Nether Largie Standing Stones, Kilmartin Glen (0.0 m; names known: False/False)
* Q5584221: Nether Largie North Cairn, Kilmartin Glen / Bruach An Druimein, Kimartin Glen (4.3 m; names known: False/False)
* Q5584221: Nether Largie North Cairn, Kilmartin Glen / Glebe Cairn, Kilmartin Glen (1.9 m; names known: False/False)
* Q5584221: Nether Largie North Cairn, Kilmartin Glen / Ri Cruin Cairn, Kilmartin Glen (0.0 m; names known: False/False)
* Q5584221: Nether Largie North Cairn, Kilmartin Glen / The Linear Cemetery, Kilmartin Glen (1.9 m; names known: False/False)
* Q5584221: Nether Largie North Cairn, Kilmartin Glen / Cup and Ring marks, Kilmartin Glen (1.9 m; names known: False/False)
* Q5584221: Nether Largie North Cairn, Kilmartin Glen / Nether Largie Mid Cairn, Kilmartin Glen (0.0 m; names known: False/False)
* Q5584221: Nether Largie South Cairn, Kilmartin Glen / Nether Largie North Cairn, Kilmartin Glen (0.0 m; names known: False/False)
* Q5584221: Nether Largie South Cairn, Kilmartin Glen / Carving depicting Animals, Kilmartin Glen (6.8 m; names known: False/False)
* Q5584221: Nether Largie South Cairn, Kilmartin Glen / Nether Largie Standing Stones, Kilmartin Glen (0.0 m; names known: False/False)
* Q5584221: Nether Largie South Cairn, Kilmartin Glen / Bruach An Druimein, Kimartin Glen (4.3 m; names known: False/False)
* Q5584221: Nether Largie South Cairn, Kilmartin Glen / Glebe Cairn, Kilmartin Glen (1.9 m; names known: False/False)
* Q5584221: Nether Largie South Cairn, Kilmartin Glen / Ri Cruin Cairn, Kilmartin Glen (0.0 m; names known: False/False)
* Q5584221: Nether Largie South Cairn, Kilmartin Glen / The Linear Cemetery, Kilmartin Glen (1.9 m; names known: False/False)
* Q5584221: Nether Largie South Cairn, Kilmartin Glen / Cup and Ring marks, Kilmartin Glen (1.9 m; names known: False/False)
* Q5584221: Nether Largie South Cairn, Kilmartin Glen / Nether Largie Mid Cairn, Kilmartin Glen (0.0 m; names known: False/False)
* Q5584221: Nether Largie Standing Stones, Kilmartin Glen / Bruach An Druimein, Kimartin Glen (4.3 m; names known: False/False)
* Q5584221: Nether Largie Standing Stones, Kilmartin Glen / Glebe Cairn, Kilmartin Glen (1.9 m; names known: False/False)
* Q5584221: Nether Largie Standing Stones, Kilmartin Glen / Ri Cruin Cairn, Kilmartin Glen (0.0 m; names known: False/False)
* Q5584221: Nether Largie Standing Stones, Kilmartin Glen / The Linear Cemetery, Kilmartin Glen (1.9 m; names known: False/False)
* Q5584221: Nether Largie Standing Stones, Kilmartin Glen / Cup and Ring marks, Kilmartin Glen (1.9 m; names known: False/False)
* Q5584221: Nether Largie Standing Stones, Kilmartin Glen / Nether Largie Mid Cairn, Kilmartin Glen (0.0 m; names known: False/False)
* Q5584221: Ri Cruin Cairn, Kilmartin Glen / The Linear Cemetery, Kilmartin Glen (1.9 m; names known: False/False)
* Q5584221: Ri Cruin Cairn, Kilmartin Glen / Cup and Ring marks, Kilmartin Glen (1.9 m; names known: False/False)
* Q5584221: Ri Cruin Cairn, Kilmartin Glen / Nether Largie Mid Cairn, Kilmartin Glen (0.0 m; names known: False/False)
* Q5584221: The Linear Cemetery, Kilmartin Glen / Cup and Ring marks, Kilmartin Glen (3.8 m; names known: False/False)
* Q5584221: The Linear Cemetery, Kilmartin Glen / Nether Largie Mid Cairn, Kilmartin Glen (1.9 m; names known: False/False)
* Q595329: Büyük Hamam / Phaselis (80.4 m; names known: False/True)
* Q632418: Archanes / Lakkos (3.1 m; names known: True/False)
* Q633757: Aspendos Theatre / Aspendos Ruins (23.4 m; names known: False/False)
* Q660692: Mortuary Temple of Hatshepsut / Hatshepsut Temple (68.3 m; names known: True/False)
* Q686289: Großmugl / The Giant Tumulus, Großmugl (2.2 m; names known: True/False)
* Q7077485: Oddendale Stone Circle / Oddendale (11.2 m; names known: False/True)
* Q737441: Templo Romano Évora / Roman Temple of Évora (51.8 m; names known: False/True)
* Q944515: Alba Fucens / Area Archeologica di Alba Fucens (89.3 m; names known: True/False)
