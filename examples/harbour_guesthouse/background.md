# BACKGROUND — Harbour Street Guesthouse v5.0

For **NEW ENGINE v5.0**. **Round-0 truth.** A deliberately small, safe world for testing: one town street, three places, three people, one errand, no hidden plots. GM-only.

```yaml
background_id: harbour_guesthouse_v1
provenance: authored
requested: []
setting:
  world: A small modern fishing town, Saltmere, on a cold northern coast. Ordinary life, no supernatural elements.
  era: present day
  starting_region: Saltmere, Harbour Street
  mode: original
  allowed_deviations: Anything ordinary people could plausibly do; nothing supernatural exists.
setting_anchors:
  peoples_or_species: [ordinary people]
  powers_or_supernatural_rules: [none]
  technology: [phones, cars, ordinary shops, a ferry to the mainland twice a day]
  institutions: [a small police post run by one constable, the harbour office, the post office]
  religions_or_beliefs: [ordinary local church-going; no effect on play]
  economics_or_trade: [fishing, a few shops, a guesthouse; cash and cards]
  law_and_social_structure: [ordinary modern law; everyone knows everyone]
  creatures_or_threats: [none beyond ordinary weather and ordinary people]
  norms:
    law_and_outlaws: [the constable keeps order; petty quarrels are settled by talking]
    morale:
      ordinary_person: breaks at the first real threat and walks away
  mp_powers: {draws_mp: [], recovery: rest_only, notes: none}
player:
  identity:
    name: Mira Dell
    age: 27
    origin: Brackwater, inland
    history:
      - Works as a courier for Brackwater Parcel Service for four years.
      - Arrived in Saltmere on the afternoon ferry with one sealed envelope to hand to Tobias Wren, the net-maker.
  appearance: Practical raincoat, rucksack, tidy dark hair, tired from the crossing.
  archetype: Courier
  job: courier
  belongs: [brackwater_parcel_service]
  gender: woman
  character: Dependable, polite, a little shy with strangers; hates leaving a job half done.
  status: Healthy and a little cold and tired.
  starting_activity: Standing at the front desk of the Harbour Street Guesthouse, about to ask for a room.
  skills:
    navigation_and_errands:
      class: NORMAL
      tier: T1
      growth_evidence: 0
      ceiling_evidence: 0
      class_source: Four years of courier work.
      abilities: []
    talking_to_strangers:
      class: NORMAL
      tier: T1
      growth_evidence: 0
      ceiling_evidence: 0
      class_source: Daily customer contact on the job.
      abilities: []
  traits: [Conscientious, easily embarrassed]
  expertise:
    established: [Finding addresses, handling parcels and signatures, reading timetables]
    limitations: [No fighting training, no special authority]
  growth_period: {opened: 0, credited: []}
  vitality: ordinary
  condition:
    hp: 10
    injuries: []
    fatigue: mildly tired
    last_rest: last night at home
  equipment:
    - {item_id: rucksack, name: rucksack, type: bag, capability_domain: carrying, condition: serviceable, special_properties: [], abilities: []}
    - {item_id: sealed_envelope, name: sealed envelope for Tobias Wren, type: parcel, capability_domain: delivery, condition: serviceable, special_properties: [], abilities: []}
    - {item_id: phone, name: phone, type: phone, capability_domain: communication, condition: serviceable, special_properties: [], abilities: []}
  money: 120
  resources: {}
  routines: {}
  fighting_style: []
  knowledge:
    facts:
      errand: The envelope must go to Tobias Wren, net-maker, at the Net Loft on Mill Lane, and he must sign for it.
      ferry: The last ferry back to the mainland leaves at 17:30 tomorrow.
    channels: [her phone, the guesthouse desk, people she meets]
content_bounds:
  depicts: [ordinary small-town life, conversation, a small errand]
  excludes: [graphic violence, supernatural events]
  notes: A gentle test world.
enabled_modules:
  numeric_level_xp: false
  equipment_power_tiers: false
  bounded_scenario_endings: false
  flexible_item_entitlement: false
locations:
  harbour_guesthouse:
    name: Harbour Street Guesthouse
    conditions: {surface: 'narrow three-storey house with a front desk, a small lounge and six rooms', smell: 'toast and sea air'}
    challenge_band: {min: 1, max: 4, basis: a quiet family guesthouse}
  harbour_street:
    name: Harbour Street
    conditions: {surface: 'wet cobbles along the quay', shops: 'a chandler, a cafe and the harbour office'}
    challenge_band: {min: 1, max: 5, basis: a public street in a small town}
  net_loft:
    name: The Net Loft, Mill Lane
    conditions: {surface: 'a long loft above a stone workshop', features: 'nets hung from beams and one stove'}
    challenge_band: {min: 1, max: 4, basis: a small craft workshop}
rights_obligations:
  courier_job: {type: duty, parties: [mira_dell, brackwater_parcel_service], state: {status: 'open; the envelope must be delivered to Tobias Wren and signed for', next: 'find Tobias Wren at the Net Loft on Mill Lane'}}
  room_booking: {type: rental, parties: [mira_dell, hobb_marren], state: {status: 'not yet booked', terms: 'a room is 45 a night, paid in cash or by card at the desk'}}
active_commitments: [courier_job]
npcs:
  hobb_marren:
    name: Hobb Marren
    job: owner of the Harbour Street Guesthouse
    belongs: []
    gender: man
    character: Easy-going, talkative, proud of his breakfasts; likes to know who is staying.
    state:
      status: behind the front desk, finishing the day's accounts
      position: harbour_guesthouse
      plan: stay at the desk until supper is served and chat with guests who come in
      due: 2026-10-05 19:00 starts serving supper
    drives: {wants: ['a full house', 'no fuss'], fears: ['bad reviews'], values: [hospitality]}
    relationships: {mira_dell: {tie: new guest, attitude: neutral, credit: [], grievance: [], believes_identity: a visitor off the ferry}}
    knowledge: {facts: {tobias_wren: 'Tobias Wren the net-maker works at the Net Loft on Mill Lane and usually works until about six'}, channels: [local gossip]}
    capability: {}
    discovered_information: {}
  tobias_wren:
    name: Tobias Wren
    job: net-maker
    belongs: []
    gender: man
    character: Gruff but fair; short on words; pays attention to paperwork.
    state:
      status: mending a trawl net in the Net Loft
      position: net_loft
      plan: keep working until about six, then lock up and walk home along Mill Lane
      due: 2026-10-05 18:00 locks up the loft
    drives: {wants: ['to finish the order for the boats'], fears: ['losing the contract'], values: [reliability]}
    relationships: {mira_dell: {tie: none yet, attitude: neutral, credit: [], grievance: [], believes_identity: unknown}}
    knowledge: {facts: {envelope: 'He is expecting a sealed envelope from the Brackwater firm'}, channels: [post, phone]}
    capability: {}
    discovered_information: {}
  edda_pryce:
    name: Edda Pryce
    job: constable of Saltmere
    belongs: []
    gender: woman
    character: Calm, observant, knows everyone by name.
    state:
      status: on her usual afternoon walk along the quay
      position: harbour_street
      plan: finish the walk and return to the police post at five
      due: 2026-10-05 17:00 returns to the police post
    drives: {wants: ['a quiet town'], fears: ['trouble with the ferry crowd'], values: [order]}
    relationships: {}
    knowledge: {facts: {}, channels: [local gossip]}
    capability: {}
    discovered_information: {}
factions: {}
quests:
  deliver_the_envelope:
    role: MAIN
    type: SHORT
    source_ref: courier_job
    objective: Deliver the sealed envelope to Tobias Wren at the Net Loft on Mill Lane and get his signature.
    status: active
    participants: [tobias_wren]
    support_refs: []
development_threads: {}
trackers: {}
active_world_pressures: {}
world_state:
  location: harbour_guesthouse
  time:
    season: autumn
    day_index: 0
    date: '2026-10-05'
    clock_minutes: 975
    daypart: late afternoon
    precision: exact
  environment: {weather: 'cold wind and fine rain', streets: 'wet cobbles', quay: 'gulls and a smell of fish'}
  material_history: []
  unowned_facts: {visible: [], hidden: []}
  glossary:
    zh_hans:
      mira_dell: Mira Dell = 米拉·戴尔
      hobb_marren: Hobb Marren = 霍布·马伦
      tobias_wren: Tobias Wren = 托拜厄斯·雷恩
      edda_pryce: Edda Pryce = 艾达·普莱斯
      harbour_guesthouse: Harbour Street Guesthouse = 海港街旅馆
      harbour_street: Harbour Street = 海港街
      net_loft: The Net Loft, Mill Lane = 磨坊巷织网阁楼
narrative_theme:
  initial: {tone: quiet and gently humorous, style: 'plain, warm, concrete'}
  current: {tone: quiet and gently humorous, style: 'plain, warm, concrete'}
```
