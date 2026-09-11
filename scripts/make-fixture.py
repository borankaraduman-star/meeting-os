"""Build real-size, FULLY synthetic Turkish meeting fixtures from a structural spec (Codex #12).

Why this exists: the 11 Sep 2026 model decision was taken on ≈2k-token fixtures and had to be reversed by
the first real 41-minute meeting, whose every chunk was ≈8–10k tokens (docs/BENCHMARK.md). A regression set
that never sees a full chunk cannot see that failure.

What goes in is a STRUCTURE, never a transcript: "one owner, one task title, a deadline that moves late in
the meeting", "a decision taken in the first chunk and reversed in the last". Everything that comes out —
people, products, cities, numbers, sentences — is invented here from word banks and an index. No real
meeting, no real correction and no paraphrase of one ever reaches this file or the fixtures it writes;
masking names in a real transcript is NOT anonymisation and is not what this does.

    .venv/bin/python scripts/make-fixture.py --list
    .venv/bin/python scripts/make-fixture.py --case late_reversal --write
    .venv/bin/python scripts/make-fixture.py --check        # regenerate every case and diff against the repo

`--check` is the offline gate: it rebuilds each case, compares it byte for byte with the file in
tests/fixtures/analysis, validates the case shape the way check_fixture_analysis does, and prints the
measured token count and chunk count per case. It sends nothing anywhere and costs nothing.
"""
import argparse,json,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meeting_os.intelligence import CHUNK_BUDGET,chunks
from meeting_os.evaluation import fixture_rows
from meeting_os.metrics import normalize

FIXTURES=Path(__file__).resolve().parents[1]/'tests/fixtures/analysis'
NOTE=('Tamamen kurgudur: kişiler, ürünler, sayılar ve cümleler scripts/make-fixture.py tarafından yapısal '
      'bir tarifden üretildi. Gerçek bir toplantının metni, düzeltmesi veya yeniden yazılmış hâli değildir. '
      'Gerçek boyutta parça ölçmek için uzundur; kısaltmak ölçtüğü şeyi ortadan kaldırır.')

# Invented people. Deliberately none of the names the real fixtures use.
PEOPLE=['Selin Arat','Kerem Doğu','Nihal Peker','Umut Serçe','Bade Kılıçer','Tolga Menteş','Yaren Aksu','Ozan Fidan']
# Invented internal system names.
TOPICS=['Kavak mobil uygulaması','Zeytin veri hattı','Poyraz ödeme ağı','Lodos arama motoru','Meltem bildirim servisi',
        'Çınar raporlama paneli','Kestane depo sistemi','Turna harita katmanı','Yelkovan zamanlayıcı','Kunduz yedekleme',
        'Sumru abonelik ekranı','Karaca kurulum sihirbazı']
METRICS=['gecikme','hata oranı','kuyruk derinliği','tamamlanma oranı','yeniden deneme sayısı','bellek kullanımı',
         'ortalama yanıt süresi','önbellek isabet oranı','işlem hacmi','günlük aktif kullanıcı sayısı']
PLACES=['Bursa','Adana','Trabzon','Eskişehir','Samsun','Denizli','Konya','Sakarya']
CHANNELS=['çağrı merkezi','mağaza panosu','saha ekibi','bayi portalı','kurumsal müşteri','test grubu']

# Observations only: past tense, measured numbers, open questions. Nothing here may read as an accepted
# commitment, because the fixture's gate counts the tasks the model returns and an extra one is a failure.
TEMPLATES=[
 '{topic} tarafında {metric} bu hafta {a} çıktı, geçen hafta {b} idi; aradaki fark {d} puan ve iki ölçüm de aynı sayaçtan geliyor.',
 '{topic} için topladığımız {n} örnekte {metric} ortalaması {a}, en kötü gün {b} oldu; medyan ise {c} seviyesinde kaldı.',
 '{topic} ekranındaki {n} kayıttan {m} tanesi {place} bölgesinden geldi, kalanı {channel} üzerinden düştü.',
 'Geçen ay {topic} üzerinde {n} değişiklik yapıldı, bunların {m} tanesi aynı hafta içinde geri alındı.',
 '{topic} testlerinde {metric} {a} seviyesinde kaldı; ölçümü üç ayrı günde tekrarladık, sonuç değişmedi.',
 '{topic} tarafında iki farklı ölçüm duruyor, biri {a} diğeri {b}; hangisinin doğru olduğunu şu an bilmiyoruz.',
 '{topic} yükü {a} üzerine çıktığında kuyruk şişiyor, {channel} tarafında bekleme {b} saniyeye kadar gidiyor.',
 '{topic} konusunda {n} kullanıcı geri bildirimi geldi, {m} tanesi aynı ekranı işaret ediyor; metinler {place} ağırlıklı.',
 '{topic} için ayrılan bütçenin {a} kısmı kullanıldı, kalan {b} kısmı duruyor; bu rakam geçen çeyrekte {c} idi.',
 '{topic} günlüklerinde {n} uyarı satırı var, {m} tanesi tek bir sunucudan; kalanlar {place} kenar düğümünde.',
 '{channel} tarafında {topic} kurulumu {k} adımda tamamlanıyor, {j} adımda kullanıcı yardım istiyor.',
 '{topic} için {a} olan hedefi geçen çeyrekte {b} olarak revize etmiştik; ölçüm bugün {c} seviyesinde.',
]


def _sentence(rng,deck,topic):
    """One observation. The template comes off a shuffled deck that is only refilled when it runs out, so the
    same sentence shape never appears twice in a row — a transcript of twelve repeated shapes is not a
    meeting, and it would hand the merge a duplicate it never has to face in real life."""
    if not deck: deck.extend(rng.sample(TEMPLATES,len(TEMPLATES)))
    template=deck.pop()
    text=template.format(topic=topic,metric=rng.choice(METRICS),place=rng.choice(PLACES),channel=rng.choice(CHANNELS),
                         a=f'{rng.randint(1,98)},{rng.randint(0,9)}',b=f'{rng.randint(1,98)},{rng.randint(0,9)}',
                         c=f'{rng.randint(1,98)},{rng.randint(0,9)}',d=f'{rng.randint(1,40)},{rng.randint(0,9)}',
                         n=rng.randint(120,9800),m=rng.randint(3,90),k=rng.randint(3,12),j=rng.randint(1,4))
    return text[:1].upper()+text[1:]


def _tokens(segments):
    """The chunker's own estimate for this transcript: bytes/3 of the item JSON it would send."""
    rows=fixture_rows({'segments':segments})
    return sum(max(1,len(json.dumps({'segment_id':r['id'],'speaker':r['speaker_name'] or r['speaker'],'text':r['text'],'uncertain':False},ensure_ascii=False).encode('utf-8'))//3) for r in rows)


class _Counter:
    """intelligence.chunks only needs `count`; this is the OpenRouter adapter's estimate, offline."""
    def count(self,text): return max(1,len(text.encode('utf-8'))//3)


def chunk_count(case):
    return len(list(chunks(fixture_rows(case),_Counter(),budget=CHUNK_BUDGET)))


def build(name,spec):
    """Filler to the target size, then the planted lines at their fractions. Deterministic: the seed is the
    case name, so the same spec always produces the same file and `--check` can diff it."""
    rng=random.Random(spec.get('seed') or sum(ord(c)*(i+1) for i,c in enumerate(name)))
    people=spec.get('people') or PEOPLE[:5]
    topics=spec.get('topics') or TOPICS[:6]
    planted=spec['planted']
    target=spec['tokens']-_tokens([{'speaker':p['speaker'],'text':p['text']} for p in planted])
    filler=[];index=0;deck=[]
    while _tokens(filler)<target:
        who=people[index%len(people)];topic=topics[(index//2)%len(topics)]
        text=' '.join(_sentence(rng,deck,topic) for _ in range(rng.randint(2,4)))
        filler.append({'speaker':who,'text':text});index+=1
    segments=list(filler)
    for item in sorted(planted,key=lambda p:-p['at']):   # back to front so earlier fractions keep their index
        segments.insert(min(len(segments),max(0,round(item['at']*len(filler)))),{'speaker':item['speaker'],'text':item['text']})
    case={'title':spec['title'],'note':NOTE+' '+spec['note'],'segments':segments,
          'expected_actions':len(spec['expected_action_fields']),
          'forbidden_action_terms':spec['forbidden_action_terms'],
          'expected_owners':[e.get('owner') for e in spec['expected_action_fields']],
          'expected_action_fields':spec['expected_action_fields']}
    if spec.get('required_decision_terms'): case['required_decision_terms']=spec['required_decision_terms']
    if spec.get('expected_topic_terms'): case['expected_topic_terms']=spec['expected_topic_terms']
    return case


def validate(name,case,spec=None):
    """Everything that can be checked without a model: the gate's own preconditions, that every planted line
    is really in the transcript, that no forbidden term hides inside an expected task title, and that a line
    planted LATE really did land in the last chunk — a reversal the model reads in chunk one measures nothing."""
    problems=[]
    if spec:
        batches=list(chunks(fixture_rows(case),_Counter(),budget=CHUNK_BUDGET))
        last={item['segment_id'] for item in batches[-1]} if batches else set()
        index={s['text']:i+1 for i,s in enumerate(case['segments'])}
        for item in spec['planted']:
            if item['at']<0.9: continue
            sid=index.get(item['text'])
            if sid is None: problems.append('geç yerleştirilen cümle transkriptte yok')
            elif sid not in last: problems.append(f'geç yerleştirilen cümle son parçada değil (segment {sid})')
    if len(case['expected_action_fields'])!=case['expected_actions']: problems.append('expected_actions sayısı alan listesiyle uyuşmuyor')
    if len(case['expected_owners'])!=case['expected_actions']: problems.append('expected_owners sayısı uyuşmuyor')
    text=normalize(' '.join(s['text'] for s in case['segments']))
    for gold in case['expected_action_fields']:
        if not gold.get('title_terms'): problems.append('title_terms boş')
        for term in gold['title_terms']:
            if normalize(term) not in text: problems.append(f'beklenen görev terimi transkriptte yok: {term}')
        if gold.get('due_text') and normalize(gold['due_text']) not in text: problems.append(f'beklenen vade metni transkriptte yok: {gold["due_text"]}')
        for term in case['forbidden_action_terms']:
            if any(normalize(term) in normalize(t) for t in gold['title_terms']): problems.append(f'yasak terim beklenen görevin içinde: {term}')
    for group in case.get('required_decision_terms') or []:
        for term in group:
            if normalize(term) not in text: problems.append(f'beklenen karar terimi transkriptte yok: {term}')
    for group in case.get('expected_topic_terms') or []:
        for term in group:
            if normalize(term) not in text: problems.append(f'beklenen konu terimi transkriptte yok: {term}')
    return problems


SPECS={
 'real_size_chunk':{
  'tokens':6600,'chunks':1,
  'title':'Kurgu test — Gerçek boyutta tek parça (haftalık ürün durumu)',
  'note':'Tek parça, ama gerçek bir toplantı parçası kadar: ≈6,6k token. Kurgu setinin geri kalanı ≈2k idi ve '
         '11 Eylül 2026 model kararı tam bu yüzden geri alındı. Ölçtüğü şey: dolu bir parçada özet 3 maddeye '
         'çökmeden bütün konuları taşıyor mu, iki taahhüt sahibi ve söylenen vadesiyle çıkıyor mu.',
  'people':['Selin Arat','Kerem Doğu','Nihal Peker','Umut Serçe'],
  'topics':['Kavak mobil uygulaması','Zeytin veri hattı','Lodos arama motoru','Meltem bildirim servisi'],
  'planted':[
   {'at':0.25,'speaker':'Selin Arat','text':'Kavak mobil uygulamasının çöküş raporunu ben hazırlayacağım, önümüzdeki çarşambaya kadar sizde olur.'},
   {'at':0.55,'speaker':'Kerem Doğu','text':'Zeytin veri hattındaki tekrar eden kayıtları ben temizleyeceğim; ay sonuna kadar bitiririm.'},
   {'at':0.7,'speaker':'Nihal Peker','text':'Lodos arama motorunda eşanlamlı sözlüğü açmaya karar verdik; bu karar bugün alındı ve uygulanacak.'},
   {'at':0.85,'speaker':'Umut Serçe','text':'Kunduz yedekleme taraması geçen ay bitti, orada kimseye iş kalmadı; sadece kapanış bilgisi.'},
  ],
  'forbidden_action_terms':['kunduz','yedekleme taraması'],
  'expected_action_fields':[
   {'title_terms':['kavak','çöküş'],'owner':'Selin Arat','due_text':'önümüzdeki çarşambaya kadar'},
   {'title_terms':['zeytin','tekrar'],'owner':'Kerem Doğu','due_text':'ay sonuna kadar'}],
  'required_decision_terms':[['lodos','eşanlamlı']],
  'expected_topic_terms':[['kavak'],['zeytin'],['lodos'],['meltem']],
 },
 'long_multi_chunk':{
  'tokens':20500,'chunks':3,
  'title':'Kurgu test — Üç parçalık uzun toplantı (çeyrek değerlendirmesi)',
  'note':'Üç gerçek boyutta parça (≈20,5k token). Ölçtüğü şey: parça birleştirmesi aynı görevi iki kez '
         'raporluyor mu, farklı parçalardaki üç ayrı taahhüt sahibiyle ve vadesiyle sağ çıkıyor mu, altı '
         'konunun hepsi özete giriyor mu.',
  'people':['Selin Arat','Kerem Doğu','Nihal Peker','Umut Serçe','Bade Kılıçer','Tolga Menteş'],
  'topics':['Kavak mobil uygulaması','Zeytin veri hattı','Poyraz ödeme ağı','Çınar raporlama paneli','Kestane depo sistemi','Turna harita katmanı'],
  'planted':[
   {'at':0.12,'speaker':'Bade Kılıçer','text':'Çınar raporlama panelinin yavaş sorgularını ben elden geçireceğim, gelecek cuma akşamına kadar hazır olur.'},
   {'at':0.45,'speaker':'Tolga Menteş','text':'Kestane depo sisteminin sayım ekranını ben yazacağım; iki hafta sonraki pazartesiye kadar teslim ederim.'},
   {'at':0.5,'speaker':'Selin Arat','text':'Turna harita katmanını belki bir gün yeniden yazarız, ama bugün kimse söz vermiyor, bu sadece bir fikir.'},
   {'at':0.82,'speaker':'Nihal Peker','text':'Poyraz ödeme ağındaki mutabakat farkını ben inceleyeceğim, ayın yirmisine kadar sonucu paylaşırım.'},
   {'at':0.9,'speaker':'Kerem Doğu','text':'Çeyrek boyunca Zeytin veri hattını tek sağlayıcıya bağlamama kararı aldık; bu karar bugün de geçerli.'},
  ],
  'forbidden_action_terms':['turna','yeniden yaz'],
  'expected_action_fields':[
   {'title_terms':['çınar','sorgu'],'owner':'Bade Kılıçer','due_text':'gelecek cuma akşamına kadar'},
   {'title_terms':['kestane','sayım'],'owner':'Tolga Menteş','due_text':'iki hafta sonraki pazartesiye kadar'},
   {'title_terms':['poyraz','mutabakat'],'owner':'Nihal Peker','due_text':'ayın yirmisine kadar'}],
  'required_decision_terms':[['zeytin','tek sağlayıcı']],
  'expected_topic_terms':[['kavak'],['zeytin'],['poyraz'],['çınar'],['kestane'],['turna']],
 },
 'late_reversal':{
  'tokens':13300,'chunks':2,
  'title':'Kurgu test — İlk parçada alınan kararın son parçada geri alınması',
  'note':'İki gerçek boyutta parça. Karar ilk parçanın başında alınıyor, son parçanın sonunda iptal ediliyor. '
         'Ölçtüğü şey: iptal ayrı bir karar olarak raporlanıyor mu (aynı maddede hem konu hem iptal), iptal '
         'edilen karardan doğan iş görev listesine sızıyor mu.',
  'people':['Yaren Aksu','Ozan Fidan','Selin Arat','Kerem Doğu','Bade Kılıçer'],
  'topics':['Poyraz ödeme ağı','Sumru abonelik ekranı','Meltem bildirim servisi','Kunduz yedekleme'],
  'planted':[
   {'at':0.06,'speaker':'Yaren Aksu','text':'Bugün şunu karara bağlıyoruz: Sumru abonelik ekranını Poyraz ödeme ağına taşıyacağız, eski hattan çıkıyoruz.'},
   {'at':0.3,'speaker':'Ozan Fidan','text':'Poyraz ödeme ağına geçiş için sunucu kirasını artırmamız gerekebilir, ama bugün bunu kimse üstlenmiyor.'},
   {'at':0.55,'speaker':'Selin Arat','text':'Meltem bildirim servisinin sessiz saat ayarını ben ekleyeceğim, önümüzdeki perşembeye kadar çıkar.'},
   {'at':0.96,'speaker':'Yaren Aksu','text':'Toplantının sonunda bir düzeltme: Sumru abonelik ekranını Poyraz ödeme ağına taşıma kararını iptal ediyoruz, eski hatta kalıyoruz.'},
  ],
  'forbidden_action_terms':['poyraz','taşı','sunucu kira'],
  'expected_action_fields':[
   {'title_terms':['meltem','sessiz'],'owner':'Selin Arat','due_text':'önümüzdeki perşembeye kadar'}],
  'required_decision_terms':[['sumru','poyraz','iptal']],
  'expected_topic_terms':[['poyraz'],['sumru'],['meltem'],['kunduz']],
 },
 'topic_coverage':{
  'tokens':6600,'chunks':1,
  'title':'Kurgu test — Dokuz ayrı konu, tek parça (kapsam ölçümü)',
  'note':'Dolu bir parçada dokuz ayrı konu konuşuluyor. Ölçtüğü şey yalnız kapsam: özet hangi konuyu düşürüyor. '
         'Gate bir görev ve bir karar bekliyor; asıl sayı expected_topic_terms üzerinden okunan eksik konu sayısıdır.',
  'people':['Nihal Peker','Umut Serçe','Bade Kılıçer','Yaren Aksu'],
  'topics':['Kavak mobil uygulaması','Zeytin veri hattı','Poyraz ödeme ağı','Lodos arama motoru','Meltem bildirim servisi',
            'Çınar raporlama paneli','Kestane depo sistemi','Yelkovan zamanlayıcı','Karaca kurulum sihirbazı'],
  'planted':[
   {'at':0.6,'speaker':'Umut Serçe','text':'Yelkovan zamanlayıcısının gece işlerini ben ayıracağım, salı sabahına kadar ayrımı bitiririm.'},
   {'at':0.75,'speaker':'Bade Kılıçer','text':'Karaca kurulum sihirbazını iki adıma indirmeye karar verdik; bu kararı bugün aldık.'},
   {'at':0.88,'speaker':'Yaren Aksu','text':'Kestane depo sistemindeki eski raf etiketleri geçen çeyrekte tamamen değiştirildi, orada açık iş yok.'},
  ],
  'forbidden_action_terms':['raf etiket'],
  'expected_action_fields':[
   {'title_terms':['yelkovan','gece'],'owner':'Umut Serçe','due_text':'salı sabahına kadar'}],
  'required_decision_terms':[['karaca','iki adım']],
  'expected_topic_terms':[['kavak'],['zeytin'],['poyraz'],['lodos'],['meltem'],['çınar'],['kestane'],['yelkovan'],['karaca']],
 },
 'owner_handover_long':{
  'tokens':13300,'chunks':2,
  'title':'Kurgu test — Uzun toplantıda sahip devri ve başkasının ağzından aktarılan söz',
  'note':'İki gerçek boyutta parça. Aynı iş ilk parçada bir kişiye veriliyor, son parçada bir başkası açıkça '
         'devralıyor; ayrıca toplantıda olmayan birinin sözü üçüncü bir ağızdan aktarılıyor. Ölçtüğü şey: '
         'devir sonrası sahip kim yazılıyor, aktarılan söz kimin görevi sayılıyor, iş iki kez mi çıkıyor.',
  'people':['Kerem Doğu','Nihal Peker','Tolga Menteş','Selin Arat','Ozan Fidan'],
  'topics':['Çınar raporlama paneli','Kavak mobil uygulaması','Lodos arama motoru','Kestane depo sistemi'],
  'planted':[
   {'at':0.1,'speaker':'Kerem Doğu','text':'Kavak mobil uygulamasının yaş sınırı ekranını ben üstleniyorum, önümüzdeki salıya kadar hazırlarım.'},
   {'at':0.4,'speaker':'Ozan Fidan','text':'Tolga dedi ki, Lodos arama motorunun yazım denetimini o bitirecekmiş; kendisi bugün toplantıda yok, onun adına söz veremeyiz.'},
   {'at':0.93,'speaker':'Nihal Peker','text':'Kavak mobil uygulamasının yaş sınırı ekranını ben devralıyorum, Kerem başka işe geçti; aynı vadeyle, önümüzdeki salıya kadar bende.'},
   {'at':0.97,'speaker':'Kerem Doğu','text':'Tamam, yaş sınırı ekranı artık Nihalde; ben o işten çıkıyorum.'},
  ],
  'forbidden_action_terms':['yazım denetimi'],
  'expected_action_fields':[
   {'title_terms':['yaş sınırı'],'owner':'Nihal Peker','due_text':'önümüzdeki salıya kadar'}],
  'required_decision_terms':[],
  'expected_topic_terms':[['kavak'],['çınar'],['lodos'],['kestane']],
 },
 'due_shift_long':{
  'tokens':13300,'chunks':2,
  'title':'Kurgu test — Uzun toplantıda vadenin sonradan kayması',
  'note':'İki gerçek boyutta parça. Bir taahhüdün vadesi ilk parçada söyleniyor, son parçada açıkça '
         'erteleniyor; ikinci bir taahhüdün vadesi hiç değişmiyor. Ölçtüğü şey: kayan vade tek görev olarak '
         've SON söylenen vadeyle mi çıkıyor, yoksa iki ayrı görev mi oluyor.',
  'people':['Bade Kılıçer','Tolga Menteş','Yaren Aksu','Selin Arat','Umut Serçe'],
  'topics':['Kestane depo sistemi','Meltem bildirim servisi','Zeytin veri hattı','Turna harita katmanı'],
  'planted':[
   {'at':0.08,'speaker':'Bade Kılıçer','text':'Kestane depo sisteminin sayaç raporunu ben çıkaracağım, bu cumaya kadar sizde olur.'},
   {'at':0.35,'speaker':'Tolga Menteş','text':'Zeytin veri hattının gece işini ben izleyeceğim, her hafta pazartesi sabahına kadar özetini geçerim.'},
   {'at':0.94,'speaker':'Bade Kılıçer','text':'Kestane sayaç raporu için bir düzeltme: bu cumaya yetişmiyor, ayın yirmi beşine kadar veriyorum; tarih değişti, iş aynı.'},
  ],
  'forbidden_action_terms':['turna'],
  'expected_action_fields':[
   {'title_terms':['kestane','sayaç'],'owner':'Bade Kılıçer','due_text':'ayın yirmi beşine kadar'},
   {'title_terms':['zeytin','gece'],'owner':'Tolga Menteş','due_text':'her hafta pazartesi sabahına kadar'}],
  'required_decision_terms':[],
  'expected_topic_terms':[['kestane'],['meltem'],['zeytin'],['turna']],
 },
}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--case',action='append',help='case name; repeatable, default all')
    p.add_argument('--write',action='store_true',help='write the case(s) into tests/fixtures/analysis')
    p.add_argument('--check',action='store_true',help='rebuild and compare with what is on disk; no writes, no network')
    p.add_argument('--list',action='store_true')
    p.add_argument('--out',type=Path,default=FIXTURES)
    args=p.parse_args(argv)
    if args.list:
        for name,spec in SPECS.items(): print(f"{name:<20} {spec['chunks']} parça  ≈{spec['tokens']} token  {spec['title']}")
        return 0
    names=[n for n in SPECS if not args.case or n in set(args.case)]
    if not names: p.error('Eşleşen kurgu senaryosu yok')
    failed=0
    for name in names:
        case=build(name,SPECS[name])
        problems=validate(name,case,SPECS[name])
        measured=chunk_count(case);tokens=_tokens(case['segments'])
        if measured!=SPECS[name]['chunks']: problems.append(f"parça sayısı {measured}, beklenen {SPECS[name]['chunks']}")
        path=args.out/f'{name}.json'
        text=json.dumps(case,ensure_ascii=False,indent=2)+'\n'
        if args.write:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
        elif args.check:
            try: current=path.read_text(encoding='utf-8')
            except OSError: problems.append('dosya yok; --write ile üretin')
            else:
                if current!=text: problems.append('dosya üretilenle aynı değil; --write ile yenileyin')
        print(f"{name:<20} {'FAIL' if problems else 'ok  '} segments={len(case['segments'])} tokens={tokens} chunks={measured} "
              f"actions={case['expected_actions']} topics={len(case.get('expected_topic_terms') or [])}")
        for problem in problems: print(f'    ! {problem}')
        failed+=bool(problems)
    return 1 if failed else 0


if __name__=='__main__': raise SystemExit(main())
