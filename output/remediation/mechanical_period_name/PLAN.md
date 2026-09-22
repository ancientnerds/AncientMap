# Phase 6 item 2 - period_name re-derived from period_start: plan

Built 2026-09-22T22:00:26+00:00 by `scripts/remediation/mechanical/period_name.py`. Lane `period-name`: run stamp `2026-09-22_mechanical-period-name`, journal test id `P6/period-name-bucket`, change keys `period-name-bucket:<site_id>`, premise `u.period_start::text`.

**220 row(s) will be written, 4784 already carry their bucket, 0 refused.** 219 of the written rows had their `period_start` corrected by phase 3; the journal row is named in each record's evidence.

The rule is the gold standard's: | `period_name` | equals `categorize_period(period_start)` | inconsistent with `period_start` |

| stored period_name | written period_name | rows |
|---|---|---|
| `1500 - 500 BC` | `500 BC - 1 AD` | 50 |
| `3000 - 1500 BC` | `1500 - 500 BC` | 34 |
| `4500 - 3000 BC` | `3000 - 1500 BC` | 31 |
| `500 BC - 1 AD` | `< 4500 BC` | 23 |
| `1 - 500 AD` | `500 BC - 1 AD` | 13 |
| `3000 - 1500 BC` | `500 BC - 1 AD` | 7 |
| `1 - 500 AD` | `< 4500 BC` | 6 |
| `< 4500 BC` | `4500 - 3000 BC` | 6 |
| `1 - 500 AD` | `500 - 1000 AD` | 5 |
| `500 BC - 1 AD` | `1500 - 500 BC` | 5 |
| `1000 - 1500 AD` | `1500+ AD` | 4 |
| `500 - 1000 AD` | `500 BC - 1 AD` | 4 |
| `1 - 500 AD` | `1500 - 500 BC` | 3 |
| `1000 - 1500 AD` | `500 - 1000 AD` | 3 |
| `3000 - 1500 BC` | `4500 - 3000 BC` | 3 |
| `4500 - 3000 BC` | `< 4500 BC` | 3 |
| `500 BC - 1 AD` | `1 - 500 AD` | 3 |
| `1 - 500 AD` | `1000 - 1500 AD` | 2 |
| `1 - 500 AD` | `1500+ AD` | 2 |
| `500 - 1000 AD` | `1 - 500 AD` | 2 |
| `500 - 1000 AD` | `1000 - 1500 AD` | 2 |
| `1000 - 1500 AD` | `1500 - 500 BC` | 1 |
| `1500 - 500 BC` | `1 - 500 AD` | 1 |
| `1500 - 500 BC` | `3000 - 1500 BC` | 1 |
| `3000 - 1500 BC` | `1500+ AD` | 1 |
| `4500 - 3000 BC` | `500 - 1000 AD` | 1 |
| `500 - 1000 AD` | `1500 - 500 BC` | 1 |
| `500 BC - 1 AD` | `1000 - 1500 AD` | 1 |
| `500 BC - 1 AD` | `3000 - 1500 BC` | 1 |
| `> 1500 AD` | `1500+ AD` | 1 |

## Every row

| site | period_start | stored | written | phase 3 |
|---|---|---|---|---|
| Abrigo de la Quebrada (`2753c6bb-1b90-4d49-8e59-b037bf1df930`) | -48800 | `1 - 500 AD` | `< 4500 BC` | yes |
| Abrigo do Lagar Velho (`88e2a4bc-8d85-4457-a1a3-22cbf01db5a2`) | -30000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Abu Simbel Temples (`392bcf2d-257f-4be6-bde4-36a26a1dbc9c`) | -1274 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Acropolis of Rhodes (`2c9bdc10-4f98-4737-bab7-fc73822d584a`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Adulis (`0349db41-4fca-4804-b614-e075164512b3`) | -1450 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Aeclanum (`ae64dd4f-971f-4fd7-8540-08af5649e67a`) | -300 | `3000 - 1500 BC` | `500 BC - 1 AD` | yes |
| Ahu Akivi (`2dab79e8-1ece-4f9b-beb3-a91573d545c3`) | 1500 | `1000 - 1500 AD` | `1500+ AD` | yes |
| Aigeira (`9ab9a6fa-2a4d-47db-8db4-237820a577d2`) | -5500 | `4500 - 3000 BC` | `< 4500 BC` | yes |
| Alba Fucens (`13120650-2e61-45af-976c-b2e0665c49af`) | -303 | `3000 - 1500 BC` | `500 BC - 1 AD` | yes |
| All Cannings Cross (`a3deb43a-0b7c-4b5c-b06a-432fa08bebac`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Amelungsburg, Süntel (`2ce50a62-f812-4204-bbb6-892a581fee52`) | 300 | `500 BC - 1 AD` | `1 - 500 AD` | yes |
| Amphipolis (`8a4ea255-abed-47fe-9c37-636756e90450`) | -437 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Ancient Kourion (`d120ca9a-703b-49e2-b333-ad6dfe508953`) | -1050 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Antas do Olival da Pêga (`c6d155e2-7202-4ee6-b29f-b3d9a440efae`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Appleby Logboat (`f336bdb9-c53b-4eed-91d2-353e9e1b4566`) | -1500 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Aquae Calidae, Bulgaria (`424eed88-76e7-402b-8d62-3f598eb9c9ce`) | -6000 | `1 - 500 AD` | `< 4500 BC` | yes |
| Arbor Low (`b3a11168-712b-445a-b453-c945be7900f3`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Artashat (`d030a021-0623-49bb-983a-e8f0ce66ea25`) | -176 | `3000 - 1500 BC` | `500 BC - 1 AD` | yes |
| Asclepieion of Athens (`629670bb-a4ec-4a5a-97a5-7623f86f46d8`) | -419 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Balamkú (`b2b1beee-00c6-4dfa-a616-89f7be1b86b7`) | -300 | `1 - 500 AD` | `500 BC - 1 AD` | yes |
| Banwolseong (`8cead41d-19f8-45cf-9dc0-144583641e4f`) | -57 | `1 - 500 AD` | `500 BC - 1 AD` | yes |
| Barbar Temple (`4d28794b-71ae-4418-b2b5-47972a341a6b`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Bayer's Lake Mystery Walls (`2fb9ef2d-55be-497a-9759-735df4f80db8`) | 1760 | `> 1500 AD` | `1500+ AD` |  |
| Belas Knap (`f0365431-b2a9-42a7-9cff-877433b51551`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Blackpatch (`dc951bdb-a70d-4346-9e7d-fdc0d908d4c5`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Blewburton Hill (`cf261948-6565-4fab-962f-c57620305e53`) | -400 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Borremose (`5281654c-51d5-443c-9a00-9824f323f61b`) | -400 | `1 - 500 AD` | `500 BC - 1 AD` | yes |
| Brauroneion (`44354857-115b-44d3-b155-cae373565602`) | -430 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Broch of Gurness (`17191c2e-9ebc-41e5-865f-1bb6be790eb5`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Bruniquel Cave (`9d58f665-8cc3-4438-9dc5-99885deb90d0`) | -176500 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Bryn Celli Ddu (`bca65486-49fb-4c72-acff-8df9d0d7f0b3`) | -4000 | `< 4500 BC` | `4500 - 3000 BC` | yes |
| Buckland Rings (`0ed9dd74-23c1-45e4-9d4e-8b80dfe46b0c`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Bull of the Corcyreans (`563693f3-5fa9-485d-940f-66f26210a9f4`) | -480 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Burnham Beeches (`6f2ea7d4-4858-46e6-a24f-0c9d49109741`) | -1000 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Butrint (`17c94d52-2df2-44ba-83f1-41c26ee6eea3`) | -1000 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Cadbury Hill (`574b24e0-9357-4d1a-a66b-556a0dfe6303`) | -1000 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Caer Drewyn (`5e5354ff-e651-496a-a9bb-cf779d3cc501`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Caesar's Camp, Bracknell Forest (`6799d014-2963-4be7-954d-6a50ebbdcbc4`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Cahal Pech (`9cd5b89c-3734-4dc0-9181-a23eaaffac23`) | -1200 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Caixa de Rotllan (`f1c3510d-e477-440e-9755-4953f31da767`) | -2500 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Carreg Coetan Arthur (`eecda91b-c255-4362-a7ed-1beac2c13869`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Carteia (`504bf30a-c4a0-48e7-8bbc-378b585b59b5`) | -940 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Carwynnen Quoit (`525dac17-d918-4dd5-9f58-6bc00715525e`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Castell de la Fosca (`661343e6-b314-4d63-9926-dd7de564aad5`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Castle Ring (`f5f8472d-d102-48b6-98b3-2d9fcfa53752`) | -500 | `1 - 500 AD` | `500 BC - 1 AD` | yes |
| Castro of Vieito (`67b015db-bcdf-4250-92e0-d43ef1237e4b`) | -100 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Cave of Aurignac (`a2720609-acca-47c5-b778-15568e68a67e`) | -45000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Cave of El Toro (`c64c62c4-89e3-4479-b27b-3853e9a81ad3`) | -5280 | `1 - 500 AD` | `< 4500 BC` | yes |
| Cave of Gabrovnica (`d36f14bc-4d2d-46a0-bcc8-9940b16adc42`) | -1200 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Cave of Niaux (`5e77ac5e-8cf2-4c79-b074-e1c61f33c8a7`) | -15000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Caves of Gargas (`2bdc9938-668f-4a33-a86f-8497b7f73e21`) | -27000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Caves of Nerja (`b5e251e7-b1d1-46d4-8bba-b02956ff13c9`) | -25000 | `1 - 500 AD` | `< 4500 BC` | yes |
| Chagres and Fort San Lorenzo (`6991377d-fbb5-4c0b-9e24-6dc294033fda`) | 1590 | `1000 - 1500 AD` | `1500+ AD` | yes |
| Chalkotheke (`9cb8e16e-1f97-47da-b7f9-558216c9b543`) | -450 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Chanctonbury Ring (`f9bb5abb-8ef2-4a21-adb5-2504fc9e87bb`) | -700 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Charax Spasinu (`4641bd18-a6d7-4f26-b895-e67f50af8e53`) | -324 | `3000 - 1500 BC` | `500 BC - 1 AD` | yes |
| Chauvet Cave (`ce8a19e4-c1b3-42e6-9bf9-4eb5600c0650`) | -32000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Cholesbury (`1706b1bf-6c89-4f31-a925-e5e679884794`) | -300 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Cholesbury Camp (`53a9ddce-054f-4471-94fd-6243611ae0a8`) | -200 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Choquequirao (`70b080a5-f192-4e17-b035-cf745251433b`) | 1500 | `1000 - 1500 AD` | `1500+ AD` | yes |
| Church of the Holy Apostles Peter and Paul, Ras (`5db5e2c0-081a-4c69-a8c6-6105ac870e5f`) | 820 | `1 - 500 AD` | `500 - 1000 AD` | yes |
| Chutixtiox (`315b648b-298b-402d-95e6-f0f79249b06f`) | 1200 | `500 - 1000 AD` | `1000 - 1500 AD` | yes |
| Cissbury Ring (`06a73089-340c-40ac-9979-4a5c08f93da5`) | -250 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Citânia de Sanfins (`d1f0267a-3e8d-4644-9b26-2e2508c49ad7`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Cividade de Âncora (`450b08c8-702f-496a-8ce0-3946c646e80a`) | -200 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Cloggs Cave (`0fc900b2-23a7-4664-ac47-0bce2852babf`) | -17000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Colossi of Memnon (`b074592e-44fe-4a6d-9bca-f8b7bd13ee69`) | -1350 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Cova Negra (`ed8ffc34-ab81-4b4d-b852-ae20205fb2b5`) | -300000 | `1 - 500 AD` | `< 4500 BC` | yes |
| Damascus Gate (`17cf019a-913c-4967-b17c-ceabe8d1ba3b`) | 1537 | `1 - 500 AD` | `1500+ AD` | yes |
| Danish Camp (`b3f1d305-9a29-43e9-ba1f-023b13ecbe6f`) | -400 | `3000 - 1500 BC` | `500 BC - 1 AD` | yes |
| Dankirke (`e7ab9b35-e0bb-4fe4-a1cb-fbe5a17c63d6`) | 300 | `500 BC - 1 AD` | `1 - 500 AD` | yes |
| Daschly (`bf02c027-74aa-4d98-909b-c58644583a2a`) | -1500 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Debdieba (`3746f91f-e0e5-4494-9ea6-0261ba241fe1`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Derinkuyu Underground City (`1c8a4914-f71e-4108-a087-dcd65fa177ca`) | -800 | `1 - 500 AD` | `1500 - 500 BC` | yes |
| Dolmen Losa de la Mora (`ff70aa7e-7371-4ffd-b673-175fd0c56ab4`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Dolmen de Bagneux (`0b994bf5-92ed-4592-a7f7-1a3d343cefd6`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Dolmen of Cunha Baixa (`0c055192-decb-4a45-a0a6-19726d9f8477`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Dos Pilas (`18f993a6-2922-432f-b795-4ef914cffcd4`) | 629 | `1000 - 1500 AD` | `500 - 1000 AD` | yes |
| Drachenhöhle (`aaf549ca-d5c7-47da-a42a-76d0806d21e9`) | -65000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Dzibanché (`184adda6-1c21-4798-aa04-7c35670a2588`) | -300 | `500 - 1000 AD` | `500 BC - 1 AD` | yes |
| Echo Stoa (`e5efe12c-25a8-423f-8974-98fc23e299e9`) | -350 | `1 - 500 AD` | `500 BC - 1 AD` | yes |
| El Caño Archaeological Park (`a5e50c3b-02dc-4f60-b94f-9f7cbd2a016e`) | -100 | `500 - 1000 AD` | `500 BC - 1 AD` | yes |
| El Ceibal (`9b213431-295d-4e12-abff-00a0fb676fe4`) | -900 | `500 BC - 1 AD` | `1500 - 500 BC` | yes |
| El Paraíso, Peru (`64d602b0-c9e8-4313-aa2b-a96ed1d7cf5f`) | -2540 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Er-Grah Tumulus (`c2628a93-7c87-4a98-8d13-8301f7063403`) | -5000 | `4500 - 3000 BC` | `< 4500 BC` | yes |
| Escoural Cave (`c96274da-bdec-445d-a79f-2a43c0688421`) | -50000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Ex voto of the Tarentines (`8c532808-61b4-4d36-ae73-0e1c6ad05982`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Falkner's Circle (`daf2b273-b9a9-4fe9-bd71-b76ff56e7671`) | -2300 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Ferrybridge Henge (`b3c4825c-79ff-48c7-bb38-015e73fc7ae2`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Font-de-Gaume (`6be9a7f1-53c8-447b-8c63-d6cc40f2281e`) | -17000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Fort Abbas (`008ecaa5-ce9b-484d-9eb8-0f27659bc91d`) | -4000 | `< 4500 BC` | `4500 - 3000 BC` | yes |
| Fortress of Niha (`a451f6be-a506-41f6-9bf7-85d8c7c7ac8e`) | 975 | `1 - 500 AD` | `500 - 1000 AD` | yes |
| Foso e Interior Citadelle De Victoria (`fad5c73f-8725-47d0-b13c-372fefba62ea`) | 1500 | `3000 - 1500 BC` | `1500+ AD` | yes |
| Ganjnameh Ancient Inscriptions (`3d801ecb-4453-4ce3-85db-dce392c67c9d`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Gnatia (`13b5bbe7-ff6b-4a1e-a8f5-d17ed3fee4f6`) | -1500 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Grange Stone Circle (`5d1b5446-41d9-46db-98c9-ac4d1996a3c1`) | -2000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Groß Raden Archaeological Open Air Museum (`9bbea428-26aa-4cb9-a9c8-d3f8f059972d`) | 800 | `1 - 500 AD` | `500 - 1000 AD` | yes |
| Großmugl (`774a99e0-e8f7-4881-aa6e-94462da0c52d`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Gårdstånga (`83abc4c8-1cdf-4429-a0f7-c9cc76f5c373`) | 900 | `4500 - 3000 BC` | `500 - 1000 AD` | yes |
| Gåseborg (`3b4ceaf0-0e07-4f25-bf33-83728e8aa49c`) | 500 | `1 - 500 AD` | `500 - 1000 AD` | yes |
| Harappa (`7fdaa528-53ef-44f1-81b0-c2112c2c1fdd`) | -3300 | `3000 - 1500 BC` | `4500 - 3000 BC` | yes |
| Harhoog (`d7c375d0-6ddc-42ed-a3d4-f128c3c1d89f`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Hembury (`786c39f1-9944-4733-93c5-4d465f5f7767`) | -4500 | `< 4500 BC` | `4500 - 3000 BC` | yes |
| Heraion of Perachora (`9d9d94a0-f338-4392-860f-983c29fabb16`) | -900 | `500 BC - 1 AD` | `1500 - 500 BC` | yes |
| Heunischenburg (`f5893102-13b9-44a0-bc87-8348f7da115c`) | -1000 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Holyhead Mountain Hut Circles (`9705b676-7ba1-465f-aebd-a21f346de5a1`) | -1000 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Huaca Huallamarca (`db227639-34b4-45db-817c-95092b4a916a`) | -200 | `500 - 1000 AD` | `500 BC - 1 AD` | yes |
| Huchuy Qosqo (`8d114f26-1360-4e96-a34a-cbe4415edb71`) | 1000 | `500 - 1000 AD` | `1000 - 1500 AD` | yes |
| Jadranovo (`77935222-436a-4bf7-9337-e7a3d86f74ba`) | -6500 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Jordbro Grave Field (`cbc93ea2-6ae5-4be6-a320-254960a60ab7`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Kavousi Kastro (`0849cdd5-5b9a-40c2-9aa9-f58c1ac32b22`) | -1200 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Kenwalch's Castle (`bc936eb9-20d2-4d52-9637-cca891a4b6e8`) | -800 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Keskese (`f292ac8c-041c-4740-906c-af202af10489`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| King John's Hill (`59aaf6d8-4d0d-424b-bfba-cadddf848c1c`) | -100 | `3000 - 1500 BC` | `500 BC - 1 AD` | yes |
| Knockmaree Dolmen (`0ac27bb1-9767-4302-bcfc-0480349aaf1b`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Koonalda Cave (`730f6c51-c41c-4f6a-9443-31acb7f007a3`) | -20000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Kow Swamp Archaeological Site (`06f6a014-f2c1-423a-8944-17c81374fd02`) | -11000 | `4500 - 3000 BC` | `< 4500 BC` | yes |
| Kuninkaanhauta (`24951d4a-ac38-4098-8f55-6e10e5a59c35`) | -1500 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| La Chaire a Calvin (`d82e4a95-00dd-4c1d-8e94-dd201f72e331`) | -13000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Labna (`042c8c7f-1ec1-485a-ba0b-3ab847320ee7`) | 200 | `500 - 1000 AD` | `1 - 500 AD` | yes |
| Lalibela (`97bdea94-4c2b-4508-83c3-777aaa16de29`) | 1200 | `500 BC - 1 AD` | `1000 - 1500 AD` | yes |
| Lapa de Gargantáns (`cfe7373f-ccbd-42a0-88db-bc19fe33d950`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Lascaux (`9b639757-cc79-496b-9748-69594f98c109`) | -22000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Laugerie-Basse (`588e9b03-5d4a-44cd-a6f4-f1de7c8ff3aa`) | -15000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Le Regourdou (`159db30a-1599-4425-8134-e0d08d164a95`) | -68000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Legananny Dolmen (`ec838509-a1e6-4f6a-b216-3f1791c16d67`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Les Combarelles (`c292f83a-933b-40e3-a658-ad7aa6c19d33`) | -11680 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Lesche of the Knidians (`b202a257-17d5-4bc3-b983-496bc68dfd40`) | -475 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Levänluhta (`533ef43f-8c4a-47bf-bdeb-d6662ae50e68`) | 400 | `1500 - 500 BC` | `1 - 500 AD` | yes |
| Little Meg (`70c04f92-593e-467b-8568-b585e1cdb58f`) | -2500 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Llwyn Bryn-Dinas (`7a0bddc9-582a-470b-a568-ecda06e46d8d`) | -900 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Maa Palaeokastro (`e1edddb2-56c8-498b-b926-78642bc312e2`) | -1300 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Macedonian Tombs, Korinos (`211bbc3a-1c61-4c8c-b5c2-0e49e027c18a`) | -400 | `1 - 500 AD` | `500 BC - 1 AD` | yes |
| Madjedbebe (`e3df9803-11c3-47ca-8cd2-39265d32470b`) | -63000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Mandbjerghøj (`56876b69-7222-4afd-8204-5f1f00bd0725`) | -1500 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Mankiala (`fa579d23-36bc-469f-9351-2be5f11e180f`) | 128 | `500 BC - 1 AD` | `1 - 500 AD` | yes |
| Marcahuamachuco (`b1a2bdd2-590d-4a2f-8168-d398739c1661`) | 400 | `500 - 1000 AD` | `1 - 500 AD` | yes |
| Mellor Hill Fort (`63220a54-b953-4e72-a914-8f564b8f3e11`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Mezhyrich, Cherkasy Oblast (`01d20059-dc53-4f51-8669-33dac18f46bb`) | -13000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Milton Keynes Hoard (`e74b1d0f-c8e8-46f2-97e6-54a05a4cf2f6`) | -1150 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Mochlos (`14dd917b-b58e-45d6-9578-bc1cefd34728`) | -3100 | `3000 - 1500 BC` | `4500 - 3000 BC` | yes |
| Monte Alban (`f7a0a44f-651b-4dfa-a500-e1a57feb2c2f`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Myrtos Pyrgos (`6c2319ca-2998-4408-a7d8-2939397c300e`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Mytilene (`f4f03f57-9987-48a4-98c0-c165e8e907fe`) | -1100 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Naranjo (`26b5802c-5fbf-4f3d-b872-7201bf027518`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Nausharo (`3191f287-4b47-4d83-903f-9815001086ed`) | -2900 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Necropolis of Carenque (`64b35e06-02b1-40d7-8931-ab1eaca02649`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Nimrod Fortress (`564bde41-2281-41fb-979e-9d75e413a845`) | -332 | `1 - 500 AD` | `500 BC - 1 AD` | yes |
| Nokalakevi (`a621b66e-1fda-41b4-9c34-d1a3e7486bd5`) | -1000 | `500 BC - 1 AD` | `1500 - 500 BC` | yes |
| Nymphaeum (Illyria) (`59addc11-6d49-46ad-ae86-608c00d56f85`) | -400 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Odigitria (`0415d29e-5239-40c6-ab1d-5b19e443336b`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Old Temple of Athena (`50fdb577-af39-425e-a038-a0f8205f66fc`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Old Winchester Hill (`a0f4690e-06d0-457b-92da-40207bfeec25`) | -600 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Older Parthenon (`2efa2892-86a4-46f7-bc3f-03c631621930`) | -490 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Olympe (`72ca2dcc-e6fc-44a2-93b1-c575e50929dc`) | -400 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Olynthus (`d5eb0b0d-1c74-4b14-aea9-a765f7a97379`) | -3000 | `1500 - 500 BC` | `3000 - 1500 BC` | yes |
| Oppidum Uetliberg (`150e64a1-8d04-49fb-b4cb-49c8b2c2fc4f`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Panamá Viejo (`ca1f8a94-27e1-4318-b3d5-3db181795ffd`) | 1519 | `1000 - 1500 AD` | `1500+ AD` | yes |
| Paracas Candelabra (`9989d873-9183-41e1-aeda-d543deb038ce`) | -200 | `1 - 500 AD` | `500 BC - 1 AD` | yes |
| Pech Maho (`548905c8-b859-40a8-9e6b-194e8b52bfe7`) | -600 | `500 BC - 1 AD` | `1500 - 500 BC` | yes |
| Pen Dinas (`0888887e-7cdb-44aa-8e48-36afb0198623`) | -300 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Petras (`53681595-1e58-4cec-99f3-0b3458769e26`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Phylaki (`71f6f6f1-0cc8-4e43-9f9f-89ae7a635ffa`) | -1400 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Piddington Roman Villa (`c70f123f-bf31-4408-8204-1b8ef717e0dd`) | -3500 | `3000 - 1500 BC` | `4500 - 3000 BC` | yes |
| Piruro (`df70e98f-a1d1-4998-966a-d9a4ee2a945f`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Preah Palilay (`41705e94-8ffd-45f3-943e-df6fac317144`) | 1100 | `1 - 500 AD` | `1000 - 1500 AD` | yes |
| Priddy Nine Barrows and Ashen Hill Barrow Cemeteries (`8b4d5105-2e39-465f-987d-78a543a5cfed`) | -2000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Priniatikos Pyrgos (`e7b1d5cc-4481-4f5e-a1b6-d759ce1bd666`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Qohaito (`941ec7f7-645f-4c87-9cc5-f156e7504054`) | -5000 | `1 - 500 AD` | `< 4500 BC` | yes |
| Quoyness Chambered Cairn (`657dbfe1-7b3f-4548-93c6-99be8674a6ff`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Ratae Corieltauvorum (`cc8b3804-e27e-4dc3-b6bf-5ffeeaef0018`) | -200 | `1 - 500 AD` | `500 BC - 1 AD` | yes |
| Revash (`a56bd06f-2305-409d-99e5-47e4f7e29ae4`) | 1301 | `1 - 500 AD` | `1000 - 1500 AD` | yes |
| Rock Carvings of Boglösa (`6de2b431-29c0-41e2-822e-91d99f46f7cb`) | -1500 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Rouffignac Cave (`424a8ef0-74a3-48ab-bdaf-8df3d957e36c`) | -11000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Sacsayhuamán (`61e8d3cd-1e93-4c78-a558-f2955a9fe221`) | 900 | `1000 - 1500 AD` | `500 - 1000 AD` | yes |
| Sanctuary of Aphrodite Urania (`b9a13520-b2dc-4bb8-80d7-10626ad9ef7a`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Sanctuary of Zeus Polieus (`9785a238-2527-4fdc-891a-93ebfcdfd9ce`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Siega Verde (`dbbef6f8-f2bb-4ea3-9691-90c09205f678`) | -20000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Skelhøj (`701203f2-92b6-4631-ab3e-aab9a5a796be`) | -1500 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Skopje Aqueduct (`d570a6d4-f4a9-4a82-856f-e66c4b55d056`) | 1600 | `1 - 500 AD` | `1500+ AD` | yes |
| Spathes (`0b2d26e4-2441-4333-900d-fc4119c03166`) | -1400 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Spirit Cave, Thailand (`9c64a3f6-8874-4441-b6c8-52428a1d45e5`) | -11000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Stoa of Zeus (`748bda90-84cd-452b-8cff-25d9185bab43`) | -425 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Stonea Camp (`c28a832f-4e26-482b-9cb1-93f5d4dce5f1`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Svingerud Runestone (`322cd09d-45f7-4cea-aaac-d1d973910935`) | -50 | `1 - 500 AD` | `500 BC - 1 AD` | yes |
| Tamtoc (`681b6f74-7b5c-4c1a-99b4-0f58822e5e39`) | -600 | `500 - 1000 AD` | `1500 - 500 BC` | yes |
| Temple of Apollo Epicurius (`7bffddb6-2fc1-49cf-987a-d7e78bdc98c5`) | -450 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Temple of Athena Nike (`8d8753ae-9935-4ffb-b578-de5907999f68`) | -420 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Temple of Athena, Paestum (`0e12027e-9a65-470f-aca7-2cb1eb408120`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Temple of Augustus and Rome (`24009e21-6345-4cee-81d6-4b6c8ae39fc4`) | -25 | `1 - 500 AD` | `500 BC - 1 AD` | yes |
| Temple of Hera, Olympia (`4c7f6521-241f-48c0-93da-f8d7893f5446`) | -600 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Temple of Poseidon, Sounion (`100ab5ea-fdf9-4d78-9f65-961ee8190b7b`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Temple of Zeus, Olympia (`349e080c-0b4f-4708-8744-d1b1c6a0b83e`) | -472 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Teotenango (`1e2fb44b-2c93-4ad8-827c-e9f1b61136ff`) | 650 | `1000 - 1500 AD` | `500 - 1000 AD` | yes |
| Tepoztlan (`62131a06-8c8c-4c55-bf8a-c19abbca2048`) | -1500 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| The Bulwarks, Porthkerry (`4e7d2543-42a8-476a-846b-f587950c12df`) | -200 | `3000 - 1500 BC` | `500 BC - 1 AD` | yes |
| The King's Grave (`d7c688fd-ca27-4a8b-91fd-affbcc948eee`) | -1400 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| The Temple of Artemis (`a939e800-06e4-4719-a000-165e7f5efe92`) | -323 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| The Trundle (`05ee235c-2ded-4af5-9e94-980c7750bc52`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Throne Room, Knossos (`ae2d2c32-689c-443f-ba05-e70023619136`) | -1500 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Tinkinswood (`446c8f5c-fbaa-4344-ae81-4b59d21f5c1a`) | -4000 | `< 4500 BC` | `4500 - 3000 BC` | yes |
| Tipón (`d2b71745-bf32-4027-8920-18fcd5600c8d`) | -1000 | `1000 - 1500 AD` | `1500 - 500 BC` | yes |
| Tomb of Leonidas (`f80ffef9-a3c9-472f-a429-dd591ce7372b`) | -430 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Treasury of the Acanthians (`a6f66111-c0d1-4c01-a49a-eb2d476a33d0`) | -424 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Turicum (`ff687661-ccd0-484c-9fe7-c966649818c0`) | -15 | `1 - 500 AD` | `500 BC - 1 AD` | yes |
| Turuñuelo (`4e399e7e-d5e9-49f8-a1de-6e404a740a55`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Ty Mawr Burial Chamber (`e77b1f25-4675-472d-b63d-ff76fae4c08d`) | -4000 | `< 4500 BC` | `4500 - 3000 BC` | yes |
| Valtos Leptokaryas (`7753067f-ce23-4def-81de-184ce34eefce`) | -1930 | `500 BC - 1 AD` | `3000 - 1500 BC` | yes |
| Vani (`ea209a12-df80-46f7-9985-4ccd0ae5fc99`) | -800 | `500 BC - 1 AD` | `1500 - 500 BC` | yes |
| Viracochapampa (`28579aa8-dab5-444d-9ee0-61c95cd1c073`) | 601 | `1 - 500 AD` | `500 - 1000 AD` | yes |
| Vix Grave (`6a7ed782-d72d-4eeb-8df6-634a27140019`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Vryokastro (`45ed713b-bab5-429b-aa62-2f26a08e2a69`) | -1200 | `3000 - 1500 BC` | `1500 - 500 BC` | yes |
| Warratyi (`a4f216bd-ef7d-4764-aa03-c88b3d5a588e`) | -49000 | `500 BC - 1 AD` | `< 4500 BC` | yes |
| Watling Temple (`ab699722-9c7e-464a-b507-74a21078411c`) | -30 | `1 - 500 AD` | `500 BC - 1 AD` | yes |
| Waulud's Bank (`1fff5c49-9169-490f-947e-bd5cc8cca4c6`) | -3000 | `4500 - 3000 BC` | `3000 - 1500 BC` | yes |
| Waun Mawn (`bf395f91-b77b-460f-802b-20cf52a73bfb`) | -3400 | `< 4500 BC` | `4500 - 3000 BC` | yes |
| Xochicalco (`16bc7c0d-247d-4de5-960c-d870236b7bb1`) | -200 | `500 - 1000 AD` | `500 BC - 1 AD` | yes |
| Yagul (`b6ecca26-a3f9-437e-bda5-aa52368598d7`) | -500 | `1500 - 500 BC` | `500 BC - 1 AD` | yes |
| Yaxhá (`4b0f332b-9289-4a80-9843-3df96b119343`) | -1000 | `1 - 500 AD` | `1500 - 500 BC` | yes |
| Zaldapa (`e7e75467-cc43-437e-9221-5ed85c050e63`) | -800 | `1 - 500 AD` | `1500 - 500 BC` | yes |

## Residuals and consumers

* `card_stats.mystery` and the card rarity read `period_name` through the combo counts; they change only when the card generator runs (Phase 6 item 4, the owner's call).
* Qdrant's change hash includes `period_name`, so the next nightly sync picks these rows up; rows whose `period_start` changed but whose label did not stay stale there (Phase 6 item 6).
* Re-run this planner after every later `period_start` write.

## Reproduce

```bash
./.venv/Scripts/python.exe scripts/remediation/mechanical/period_name.py --write
./.venv/Scripts/python.exe -m pytest tests/remediation/test_mechanical_period_name.py -q -rs
```
