"""Compare mechanics.py with the V5 helper on many inputs: python tools/compare_v5.py path/to/engine_math_v5_0.py"""
import sys, types, random, importlib.util
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
from localgm import mechanics as M, clock
spec=importlib.util.spec_from_file_location('old',sys.argv[1]); old=importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
NS=types.SimpleNamespace
bad=0
for a in range(1,30):
  for c in range(1,30):
    if M.capmod(a,c)!=old.capmod(a,c): bad+=1
for base in range(1,21):
  for cap in M.CAP_BANDS:
    for fit in range(-2,3):
      for env in (-1,0,1,2):
        for tm in (0,1):
          d=M.difficulty(base,{'environment':env,'time':tm}); t=M.tool_mod(fit,0)
          r=old.do_check(NS(environment=env,time=tm,sensory=0,position=0,simultaneous=0,fit=fit,condition=0,cmp=None,challenge=None,capmod=cap,base=base,odds=True,brief=False,lite=False,label='',on_failure='',stakes='',tool_source='',basis=''))
          if r['odds_percent']!=M.odds(cap,t,d) or r['difficulty']!=d: bad+=1
for lv in range(1,35):
  for xp in (0,50,125):
    for amt in (0,100,5000):
      r=old.do_xp(NS(level=lv,xp=xp,amount=amt,r=None,p=None,scope=None))
      if (r['new']['level'],r['new']['xp'])!=M.add_xp(lv,xp,amt)[:2]: bad+=1
  for R in range(1,40):
    for s in M.SCOPE:
      r=old.do_xp(NS(level=lv,xp=0,amount=None,r=R,p=lv,scope=s))
      if r['award']!=M.xp_award(R,lv,s): bad+=1
for v in range(1,20):
  for sz in M.SIZE_MULT:
    if old.do_vitals(NS(v=v,size=sz,mp_tier=None))['max_hp']!=M.max_hp(v,sz): bad+=1
for hp in range(0,21):
  for dmg in (0,3,7,12,25):
    for soak in (0,2):
      r=old.do_harm(NS(max=20,hp=hp,dice=None,amount=dmg,soak=soak,hits=2,who='',brief=False))
      m=M.harm(hp,20,[dmg,dmg],soak)
      if (r['hp'],r['state'],r['lasting_injury'])!=(m['hp'],m['state'],m['lasting_injury']): bad+=1
for cls in M.CEILING:
  for tier in M.TIERS:
    if M.TIERS.index(tier)>M.TIERS.index(M.CEILING[cls]): continue
    for ev in (0,9,10,25,60,100):
      for ce in (0,19,40):
        for cs in (False,True):
          r=old.do_boundary(NS(cls=cls,tier=tier,evidence=ev,ceiling_evidence=ce,class_source=cs))['new']
          m=M.grow(cls,tier,ev,ce,cs)
          if (r['class'],r['tier'],r['growth_evidence'],r['ceiling_evidence'])!=(m['class'],m['tier'],m['growth_evidence'],m['ceiling_evidence']): bad+=1; print(cls,tier,ev,ce,cs,r,m)
for clock_ in (0,100,1400):
  for add in (0,50,500,3000):
    r=old.do_time(NS(day=3,clock=clock_,add=add)); n,d=clock.advance({'day_index':3,'clock_minutes':clock_},add)
    if (r['day_index'],r['clock_minutes'],r['days_rolled'])!=(n['day_index'],n['clock_minutes'],d): bad+=1
print('mismatches',bad)
