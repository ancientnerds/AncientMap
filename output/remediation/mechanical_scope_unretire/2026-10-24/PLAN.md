# Scope un-retire (D58, D50) - wave 2026-10-24

Built 2026-10-24T16:54:49+00:00 by `scripts/remediation/mechanical/scope_unretire.py` from the export of 2026-10-24 16:54:44.464227+00. Lane `scope-unretire-2026-10-24`, run stamp `2026-10-24_mechanical-scope-unretire`, test id `D58/scope-unretire`.

```json
{
 "cells": 18,
 "d50_disputed": 0,
 "d58_date": 8,
 "d58_museum": 1,
 "left_for_later_waves": 0,
 "sites": 9,
 "skipped": 75,
 "skipped_d50-no-dispute-text": 6,
 "skipped_label-borderline": 4,
 "skipped_museum-exhibits-out": 2,
 "skipped_not-a-date-retirement": 21,
 "skipped_not-a-site-question-first": 1,
 "skipped_outside-label-window": 41,
 "wave_sites": 9
}
```

## Un-retired

* **Prambanan Temple** (`21bd525e-fe10-40dd-96be-32d3c8d36d26`): D58 label rule (owner, 2026-10-24): rest of world, period_start 850 lies inside its window through 1500 AD; the E3 retirement no longer holds
  * remediation_change_log:42576: 2026-09-23_mechanical-scope-e4: scope_status None -> retired
  * pipeline/normalizers/dates.py: rest of world
* **Preah Palilay** (`41705e94-8ffd-45f3-943e-df6fac317144`): D58 label rule (owner, 2026-10-24): rest of world, period_start 1100 lies inside its window through 1500 AD; the E3 retirement no longer holds
  * remediation_change_log:42600: 2026-09-23_mechanical-scope-e4: scope_status None -> retired
  * pipeline/normalizers/dates.py: rest of world
* **Bhagwan Bharat's Statue** (`59267588-ef6b-40b7-9990-c93b2b6d08f4`): D58 label rule (owner, 2026-10-24): rest of world, period_start 900 lies inside its window through 1500 AD; the E3 retirement no longer holds
  * remediation_change_log:42626: 2026-09-23_mechanical-scope-e4: scope_status None -> retired
  * pipeline/normalizers/dates.py: rest of world
* **Khushuu Tsaidam Museum** (`71d8e2bc-7406-4c4a-b68d-2ff1b71800e8`): D58 label rule (owner, 2026-10-24), museum rule: its exhibits (Gokturk Orkhon stelae, 8th century) lie in the rest of world, inside the window through 1500 AD; the E3 retirement no longer holds
  * remediation_change_log:42642: 2026-09-23_mechanical-scope-e4: scope_status None -> retired
  * unified_sites.scope_reason: Gokturk Orkhon stelae, 8th century
  * pipeline/normalizers/dates.py: rest of world
* **Great Kyz Kala** (`78a48265-c951-4c65-b513-f39467b85d50`): D58 label rule (owner, 2026-10-24): rest of world, period_start 750 lies inside its window through 1500 AD; the E3 retirement no longer holds
  * remediation_change_log:42648: 2026-09-23_mechanical-scope-e4: scope_status None -> retired
  * pipeline/normalizers/dates.py: rest of world
* **Buddhist Rock Carving in Manglawar** (`916b8b05-0c42-4af3-b05e-9be842a23c5b`): D58 label rule (owner, 2026-10-24): rest of world, period_start 600 lies inside its window through 1500 AD; the E3 retirement no longer holds
  * remediation_change_log:42672: 2026-09-23_mechanical-scope-e4: scope_status None -> retired
  * pipeline/normalizers/dates.py: rest of world
* **Kameishi** (`9b5751dd-d54e-4e8a-b4c0-7b4dc2a863c7`): D58 label rule (owner, 2026-10-24): rest of world, period_start 600 lies inside its window through 1500 AD; the E3 retirement no longer holds
  * remediation_change_log:42680: 2026-09-23_mechanical-scope-e4: scope_status None -> retired
  * pipeline/normalizers/dates.py: rest of world
* **Gondrani (Shehr-e-Roghan)** (`f91d645f-29ad-439d-83eb-fdf0531d93cc`): D58 label rule (owner, 2026-10-24): rest of world, period_start 700 lies inside its window through 1500 AD; the E3 retirement no longer holds
  * remediation_change_log:42754: 2026-09-23_mechanical-scope-e4: scope_status None -> retired
  * pipeline/normalizers/dates.py: rest of world
* **Sakafune-ishi Ruins** (`fc029995-b6bb-4375-a5fa-9a0eb7d0fa85`): D58 label rule (owner, 2026-10-24): rest of world, period_start 655 lies inside its window through 1500 AD; the E3 retirement no longer holds
  * remediation_change_log:42760: 2026-09-23_mechanical-scope-e4: scope_status None -> retired
  * pipeline/normalizers/dates.py: rest of world

## Not un-retired

* **Yonaguni Monument** (`01296632-a2a1-4610-a4a9-d0c3be77b788`): `d50-no-dispute-text` - D50 shows it only with a sourced dispute text (lane E, `wc/disputes.py`): journal row 168796 is no lane-E enrichment ('O5 2026-09-26: Satzweise pruefen und kuerzen')
* **Olympos Ruins** (`04d8ce82-4fa3-4e48-88b7-bb41b354260c`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:00f522ff-8e1b-4983-961c-ef6cb1ff27d1': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Sahasralinga** (`075337ec-9108-431f-ae90-d5d0e795f23a`): `outside-label-window` - date 1678 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Templo Romano Évora** (`07fb4e2f-26e5-4720-a949-9c28d4712e11`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:9152beea-f7ab-40ef-a692-ef63ac8e9ca6': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Çem Kalesi** (`0943934a-6b61-416c-a382-8493a2d9db7f`): `label-borderline` - Türkiye, date 900: the label decides (a Byzantine, Crusader or Norse subject is out) - a scope verdict, not this lane
* **Bosnian Pyramid of the Moon** (`0fd636ac-1a80-4a77-b9d0-a065ae811656`): `d50-no-dispute-text` - D50 shows it only with a sourced dispute text (lane E, `wc/disputes.py`): journal row 169354 is no lane-E enrichment ('O5 2026-09-26: Satzweise pruefen und kuerzen')
* **Ruther Cross** (`10fc71fe-5305-497e-8642-4219e822223a`): `outside-label-window` - date 1200 is past the medieval Old World cutoff of 500 AD: the retirement stands
* **Area Archeologica di Alba Fucens** (`13c3f25f-3887-49c1-9492-cf7e512e5782`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:13120650-2e61-45af-976c-b2e0665c49af': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Mookambika Wildlife Sanctuary Kodachadri** (`2133d54c-f352-4325-ae0c-dd532f9a65d3`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as "E3: no date, and its own source places it outside the window: Its own source describes a wildlife sanctuary created in 1974 and names no ancient site; the 2026-09-19 assessment listed it among the clear exclusions. site_type holds the marker 'suspect_modern'.": not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Archaeological Site, Heraion** (`24676ed3-9308-42d4-bf35-1c739f0652e2`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:9d9d94a0-f338-4392-860f-983c29fabb16': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Manora Fort, Karachi (Qasim Fort)** (`2dfb1bee-9ec5-4eb6-b8b7-cfedbcb09744`): `outside-label-window` - date 1797 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Bayer's Lake Mystery Walls** (`2fb9ef2d-55be-497a-9759-735df4f80db8`): `outside-label-window` - date 1760 is past the Americas cutoff of 1500 AD: the retirement stands
* **Midford Castle** (`32429f3c-6e14-4015-900a-a9cd9fbb81eb`): `outside-label-window` - date 1775 is past the medieval Old World cutoff of 500 AD: the retirement stands
* **Naegi Castle Ruins** (`35e015d9-6ab6-4763-9873-0ff2560b9b91`): `outside-label-window` - date 1532 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Oudong** (`37f08947-0576-48de-90ca-ef211b615619`): `outside-label-window` - date 1601 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Landguard Fort** (`39f7cab4-e0d9-4c15-a4a0-8fccd461ba3b`): `outside-label-window` - date 1540 is past the medieval Old World cutoff of 500 AD: the retirement stands
* **Bosnian Pyramid of the Sun** (`3c466fde-b751-4065-8de2-bd5c9280afe5`): `d50-no-dispute-text` - D50 shows it only with a sourced dispute text (lane E, `wc/disputes.py`): journal row 336505 is no lane-E enrichment ('O5 2026-09-26: Satzweise pruefen und kuerzen')
* **Forte de Santa Luzia** (`3ff2ae0e-9095-48ed-a45e-0d8c9f455527`): `outside-label-window` - date 1641 is past the medieval Old World cutoff of 500 AD: the retirement stands
* **Overton Down** (`414416be-0a81-45f7-a572-216f39ee6a0d`): `outside-label-window` - date 1960 is past the medieval Old World cutoff of 500 AD: the retirement stands
* **Belenkeşlik Castle** (`42ddb06e-547a-4f8e-b093-a6efcf2a8e2c`): `label-borderline` - Türkiye, date 1100: the label decides (a Byzantine, Crusader or Norse subject is out) - a scope verdict, not this lane
* **The Aqueduct of Jerwan** (`4687a49a-c987-4c56-bc6e-5094aa57667d`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:c6d9487d-d138-4d73-beb1-5735e50da048': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Forte de Nossa Senhora da Graça** (`46bceb53-3c23-41a6-9659-b7a67035197a`): `outside-label-window` - date 1763 is past the medieval Old World cutoff of 500 AD: the retirement stands
* **Nossa Senhora da Boa Estrela** (`46c6cf72-8616-4f4c-8993-73c50abdd6a5`): `outside-label-window` - date 1946 is past the medieval Old World cutoff of 500 AD: the retirement stands
* **Tarxien Temples** (`4a5a324f-832f-4dca-b688-d4a006d297c7`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:318414bc-098b-4459-95c0-41e1ec49c8a8': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Coricancha** (`4e6247b0-7416-413f-b7a3-b31890a45f3b`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:4a9b3802-1067-4f6b-a144-4c2ffe9619a4': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Sundarnarayan Temple** (`5067da0a-d681-4fe3-91e5-e2dc7c0656d7`): `outside-label-window` - date 1756 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Tomb of Jahangir** (`50e5e380-1f89-4fa3-88de-e6ad35241316`): `outside-label-window` - date 1627 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Archaeological Site of Kition** (`55a670ec-c7c5-4f52-98ea-b25211aedd4e`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:47c37ef9-98ee-41d8-879b-e78db06295da': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Augusta Bilbilis** (`577b13cd-242b-4951-a8c4-ab3ecde0e5b1`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:23576019-c749-4ee9-95b1-cdae21f5ff06': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Tomb of Ali Mardan Khan** (`58d46ab0-7fc9-4dfa-bf40-a5042d4a91be`): `outside-label-window` - date 1630 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Dodona** (`5a04d6f3-c82d-4c82-b1e9-3d70bff135ae`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:56f594fc-6819-4d51-98a4-1cf5b4a265a6': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **East Bay Walls** (`5f8ce412-3bb0-4aa3-aff3-cd1d825273a6`): `outside-label-window` - date 1850 is past the Americas cutoff of 1500 AD: the retirement stands
* **Kagoshima Castle Ruins** (`6791baaf-bb36-462b-a497-e704e23251ac`): `outside-label-window` - date 1601 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Chagres and Fort San Lorenzo** (`6991377d-fbb5-4c0b-9e24-6dc294033fda`): `outside-label-window` - date 1590 is past the Americas cutoff of 1500 AD: the retirement stands
* **Hattuşa Örenyeri** (`7e33b1ac-bb32-4b6c-b070-2c4fdcaf19fb`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:109fcdea-c114-4143-87ac-77c4c9c20f16': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Krishnabai Mandir** (`826407f8-35ca-4423-bd85-5f53a3d95ea2`): `outside-label-window` - date 1888 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Richat Structure** (`84b456ff-0b44-4d75-92a4-5cbe22026b95`): `d50-no-dispute-text` - D50 shows it only with a sourced dispute text (lane E, `wc/disputes.py`): journal row 81058 is no lane-E enrichment (None)
* **Jamrud Fort** (`8a42154e-7081-481f-ad77-49e7a02b2c98`): `outside-label-window` - date 1836 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Ali Masjid Fort** (`8c159d7f-d954-44fc-aab9-6b7841d68a35`): `outside-label-window` - date 1837 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Pinara Antique City** (`8cecb38f-08cf-4a93-b350-9ccbb74109bb`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:5025eee3-28ea-46d6-b2c3-dbb1f38a24d6': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Bosnian Pyramid of Love** (`8df8659c-49be-4a66-b25a-ecbf96541515`): `d50-no-dispute-text` - D50 shows it only with a sourced dispute text (lane E, `wc/disputes.py`): no journal row wrote the description the site holds now
* **Termantia** (`93391ee6-8e80-42db-922c-11f64ea57db9`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:84ef64f3-394a-4b35-ba4a-7e81b3b6a317': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Mount Livadiyskaya** (`97b3cd09-f833-48ca-8273-8b76767fc245`): `not-a-site-question-first` - site_type 'Natural feature' asks the scope review's not-a-site question first: the retirement stands until it is answered
* **Kot Diji Fort** (`98cb1e3f-2eab-4bd0-9cda-8bd61abcacb6`): `outside-label-window` - date 1795 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Groß Raden Archaeological Open Air Museum** (`9bbea428-26aa-4cb9-a9c8-d3f8f059972d`): `museum-exhibits-out` - its exhibits (Slavic settlement and temple, 9th/10th century) are of the medieval Old World: the retirement stands
* **Shanqal Fort** (`9f823459-f4ce-43cc-a433-b1cdaf9f89ad`): `outside-label-window` - date 1737 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Chrobry Fortified Village** (`a26993c6-b562-4c28-a584-8de2c9312dad`): `outside-label-window` - date 1000 is past the medieval Old World cutoff of 500 AD: the retirement stands
* **Osaka Castle** (`a3fdb1d8-083b-4e8f-a170-5b98638d5b53`): `outside-label-window` - date 1583 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Fortress of Niha** (`a451f6be-a506-41f6-9bf7-85d8c7c7ac8e`): `label-borderline` - Lebanon, date 975: the label decides (a Byzantine, Crusader or Norse subject is out) - a scope verdict, not this lane
* **Ksar el Barka** (`a5d9e9a7-9fd2-4a0f-a3ae-7dd78fba429b`): `outside-label-window` - date 1690 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Charents Arch** (`a9d840ac-4636-40bf-9570-682550967728`): `outside-label-window` - date 1957 is past the rest of world cutoff of 1500 AD: the retirement stands
* **King Richard III Visitor Centre** (`aa56465b-1a9e-45b2-abec-b50be3796d8f`): `museum-exhibits-out` - its exhibits (the 1485 grave of Richard III) are of the medieval Old World: the retirement stands
* **Dolmen of Menga** (`ab03fa75-bbdc-46a2-ba55-25e2f5edd5c4`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:485c3c0c-31f0-45a7-a06b-797c4c021466': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Shri Bhagwan Bahubali Monolithic Statue** (`abfa8b60-ea29-4150-925f-87d4b1fe8092`): `outside-label-window` - date 1973 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Lëkurësi Castle** (`af9036d8-9a13-4107-b22d-b5c088006d91`): `outside-label-window` - date 1537 is past the medieval Old World cutoff of 500 AD: the retirement stands
* **Bishop's Basilica of Philippopolis** (`b46b6969-3160-4cbd-a574-8727ee7c53c5`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:891ad351-7985-4c16-b6a6-830c26bc268f': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Popping Stone** (`b89bd9e5-053b-4d85-a2a9-1f79a6c3b452`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'E3: no date, and its own source places it outside the window: Natural boulders whose only human history in the source is the 1797 legend; the 2026-09-19 assessment listed it among the clear exclusions.': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Sheikhupura Fort** (`b9f26550-7988-4a34-a3ff-7ef9cb69c838`): `outside-label-window` - date 1607 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Naukot Fort** (`bc10d0af-75ab-4c01-8b2c-a00327d0bb80`): `outside-label-window` - date 1810 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Whiteleaf Cross** (`c54a5e46-c856-46be-b638-62d6fda1c8e5`): `outside-label-window` - date 1650 is past the medieval Old World cutoff of 500 AD: the retirement stands
* **Baltic Sea Anomaly** (`c8d2c13e-fd9a-466c-9fdc-fc26ee798ded`): `d50-no-dispute-text` - D50 shows it only with a sourced dispute text (lane E, `wc/disputes.py`): journal row 91892 is no lane-E enrichment (None)
* **Jaffa Gate** (`c932b4f9-283e-4756-b9aa-cc5491aaddf8`): `outside-label-window` - date 1538 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Ciudad Romana de Cáparra** (`cf49332c-0a05-4ba7-bf4f-48a703ee7a1e`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:577f2ec4-3dc0-4d10-9425-39f1cb654009': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Attock Fort** (`cf7e7df8-8987-4989-9fd5-d506d1844669`): `outside-label-window` - date 1580 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Ancient Kourion** (`d120ca9a-703b-49e2-b333-ad6dfe508953`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:9983bdce-9f35-47a3-a570-4021cfa41b97': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Yenikale Ruins** (`d6d44645-a99b-4826-85b3-eb0123faadd2`): `outside-label-window` - date 1699 is past the medieval Old World cutoff of 500 AD: the retirement stands
* **Xhamia e Plumbit** (`e284429d-db64-478d-becd-20faf2a1b847`): `outside-label-window` - date 1733 is past the medieval Old World cutoff of 500 AD: the retirement stands
* **Koe Thaung Pagoda** (`e514dc13-8bd1-443b-8137-94ff173d32b8`): `outside-label-window` - date 1554 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Ukonkivi** (`eaac27c7-d027-442a-ae0d-49d9e27dfb69`): `outside-label-window` - date 1100 is past the medieval Old World cutoff of 500 AD: the retirement stands
* **Parque Nacional de Shorsky** (`eb80c959-82f5-4288-9a3d-02c2695e583a`): `outside-label-window` - date 1989 is past the rest of world cutoff of 1500 AD: the retirement stands
* **Montjuïc Castle** (`ed05c23a-973b-4d69-923c-b2e7b1b97305`): `outside-label-window` - date 1641 is past the medieval Old World cutoff of 500 AD: the retirement stands
* **Archaeological Park Carnuntum** (`f3da4b6e-c4a3-4416-9c28-93bf761119ad`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:1531d4a1-bb24-4727-9b25-f2089088acaf': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Dooey's Cairn** (`f5ca382a-3725-4cbb-961a-6afbf5c21507`): `not-a-date-retirement` - retired by 2026-09-23_mechanical-scope-e4 as 'duplicate_of:f6b6e039-36f1-4107-b730-dc2aa34b7a92': not for a date past its cutoff nor by the museum rule, so D58 does not take it back
* **Dara Fortress** (`f993864c-339b-4a13-b85c-59a59737df2c`): `label-borderline` - Türkiye, date 750: the label decides (a Byzantine, Crusader or Norse subject is out) - a scope verdict, not this lane
* **Olsborg Castle** (`f9ad013b-8208-4a02-8480-7c865c7577f6`): `outside-label-window` - date 1502 is past the medieval Old World cutoff of 500 AD: the retirement stands
