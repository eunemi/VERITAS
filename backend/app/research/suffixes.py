"""Which part of a hostname identifies a *publisher*.

``www.bbc.co.uk`` and ``bbc.co.uk`` are one publisher; ``alice.substack.com`` and
``bob.substack.com`` are two. Neither fact can be worked out by counting dots, and
both matter here, because independence is counted per publisher: a claim
corroborated by ``bbc.co.uk`` and ``news.bbc.co.uk`` has one source behind it, and
a claim corroborated by two Substack authors has two.

The reference answer is the Mozilla Public Suffix List, and this is not it. The PSL
is ~15 000 rules that change weekly, and the two Python libraries that read it
(``publicsuffix2``, ``tldextract``) are not installable here — so what follows is a
curated table covering the suffixes a news-and-fact-checking corpus actually
lands on. It is knowingly incomplete, and that is safe for one specific reason.

**Every error caused by incompleteness understates independence; only a false
entry overstates it.** Omit ``co.uk`` and ``bbc.co.uk`` collapses to ``co.uk``, so
the BBC and the Guardian read as one publisher — two real sources counted as one,
which makes corroboration look *weaker* than it is. Omit ``substack.com`` and two
authors read as one publisher — again weaker. But wrongly *add* ``nytimes.com``
and ``www.nytimes.com`` becomes its own publisher, so one source reads as several,
which makes corroboration look **stronger** than it is. The first kind of mistake
is a conservative undercount. The second is the dossier overstating its own
evidence, which is the failure this whole service exists to avoid.

So the rule for this table is: an entry goes in only when each label beneath it is
genuinely a different party. That is the substantive question — the PSL is the
best-known implementation of it, not its definition — and it is why
:data:`MULTI_TENANT` includes hosts on their own merits rather than by checking
membership of a list this module cannot read. Being incomplete is acceptable.
Being speculative is not.

Nothing here is deduplication. Two publishers are still two sources even when they
carry the same wire copy; see :mod:`app.research.dedupe` for what merges and what
is merely marked.

Upgrading to the real list
--------------------------
Add ``publicsuffix2`` to ``requirements.txt`` and replace
:func:`app.research.urls.registrable_domain`'s table lookup with it. If you reach
for ``tldextract`` instead, construct it as
``tldextract.TLDExtract(suffix_list_urls=())`` — by default it fetches the list
over HTTP on first use and caches it to disk, which inside a request handler is a
network call nobody asked for and a startup that fails when the network is down.
Either way, keep this module's tests: they encode the behaviour the application
depends on, and they should pass unchanged against a real implementation.
"""

from __future__ import annotations

# ---------------------------------------------------------------------- icann ----
#
# Multi-label registry suffixes: registries that sell names one level further down
# than the TLD. Single-label TLDs need no data at all — the default rule already
# reads the last label as the suffix, so `example.com` and `example.de` come out
# right with nothing listed here.

_UK = ("co.uk", "org.uk", "me.uk", "ltd.uk", "plc.uk", "net.uk", "sch.uk",
       "ac.uk", "gov.uk", "nhs.uk", "police.uk", "mod.uk")

_IE = ("gov.ie",)

_AU = ("com.au", "net.au", "org.au", "edu.au", "gov.au", "asn.au", "id.au",
       "csiro.au")

_NZ = ("co.nz", "net.nz", "org.nz", "govt.nz", "ac.nz", "school.nz", "geek.nz",
       "kiwi.nz", "maori.nz", "iwi.nz", "health.nz", "cri.nz", "parliament.nz",
       "mil.nz")

_ZA = ("co.za", "org.za", "net.za", "gov.za", "ac.za", "web.za", "edu.za",
       "mil.za", "nom.za")

_IN = ("co.in", "net.in", "org.in", "gen.in", "firm.in", "ind.in", "gov.in",
       "nic.in", "ac.in", "edu.in", "res.in", "mil.in")

_JP = ("co.jp", "or.jp", "ne.jp", "ac.jp", "ad.jp", "ed.jp", "go.jp", "gr.jp",
       "lg.jp")

_KR = ("co.kr", "or.kr", "ne.kr", "re.kr", "pe.kr", "go.kr", "mil.kr", "ac.kr",
       "hs.kr", "ms.kr", "es.kr", "sc.kr", "kg.kr")

_CN = ("com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "ac.cn", "mil.cn")

_HK = ("com.hk", "net.hk", "org.hk", "gov.hk", "edu.hk", "idv.hk")

_TW = ("com.tw", "net.tw", "org.tw", "gov.tw", "edu.tw", "idv.tw", "game.tw",
       "ebiz.tw", "club.tw")

_SG = ("com.sg", "net.sg", "org.sg", "gov.sg", "edu.sg", "per.sg")

_MY = ("com.my", "net.my", "org.my", "gov.my", "edu.my", "mil.my", "name.my")

_ID = ("co.id", "net.id", "or.id", "web.id", "sch.id", "ac.id", "go.id",
       "mil.id", "my.id", "biz.id", "desa.id", "ponpes.id")

_PH = ("com.ph", "net.ph", "org.ph", "gov.ph", "edu.ph", "mil.ph", "ngo.ph")

_TH = ("co.th", "net.th", "or.th", "ac.th", "go.th", "mi.th", "in.th")

_VN = ("com.vn", "net.vn", "org.vn", "gov.vn", "edu.vn", "ac.vn", "biz.vn",
       "info.vn", "name.vn", "pro.vn", "health.vn", "int.vn")

_PK = ("com.pk", "net.pk", "org.pk", "gov.pk", "edu.pk", "biz.pk", "web.pk",
       "fam.pk", "gob.pk", "gok.pk", "gop.pk", "gos.pk")

_BD = ("com.bd", "net.bd", "org.bd", "gov.bd", "edu.bd", "ac.bd", "info.bd",
       "mil.bd")

_LK = ("com.lk", "net.lk", "org.lk", "gov.lk", "edu.lk", "ac.lk", "sch.lk",
       "ngo.lk", "soc.lk", "web.lk", "ltd.lk", "assn.lk", "grp.lk", "hotel.lk")

_NP = ("com.np", "net.np", "org.np", "gov.np", "edu.np", "mil.np", "info.np")

_IL = ("co.il", "net.il", "org.il", "ac.il", "gov.il", "muni.il", "k12.il",
       "idf.il")

_TR = ("com.tr", "net.tr", "org.tr", "gov.tr", "edu.tr", "mil.tr", "k12.tr",
       "bel.tr", "biz.tr", "gen.tr", "info.tr", "name.tr", "pol.tr", "tel.tr",
       "tsk.tr", "tv.tr", "web.tr", "av.tr", "dr.tr", "bbs.tr")

_RU = ("com.ru", "net.ru", "org.ru", "pp.ru", "msk.ru", "spb.ru", "ac.ru",
       "edu.ru", "gov.ru", "int.ru", "mil.ru", "test.ru")

_UA = ("com.ua", "net.ua", "org.ua", "gov.ua", "edu.ua", "in.ua", "co.ua",
       "kiev.ua", "lviv.ua", "odessa.ua")

_PL = ("com.pl", "net.pl", "org.pl", "gov.pl", "edu.pl", "biz.pl", "info.pl",
       "waw.pl", "gda.pl", "krakow.pl", "wroclaw.pl", "poznan.pl", "lodz.pl")

_CZ_SK = ()  # both registries are flat: `example.cz`, `example.sk`.

_RO = ("com.ro", "org.ro", "tm.ro", "nt.ro", "nom.ro", "info.ro", "rec.ro",
       "store.ro", "arts.ro", "firm.ro", "www.ro")

_RS = ("co.rs", "org.rs", "edu.rs", "ac.rs", "gov.rs", "in.rs")

_HR = ("com.hr", "iz.hr", "from.hr", "name.hr")

_MK = ("com.mk", "org.mk", "net.mk", "edu.mk", "gov.mk", "inf.mk", "name.mk")

_AL_BA = ("com.al", "edu.al", "gov.al", "mil.al", "net.al", "org.al",
          "com.ba", "edu.ba", "gov.ba", "mil.ba", "net.ba", "org.ba")

_ME = ("co.me", "net.me", "org.me", "edu.me", "ac.me", "gov.me", "its.me",
       "priv.me")

_EE = ("co.ee", "pri.ee", "fie.ee", "med.ee", "org.ee", "gov.ee", "riik.ee",
       "edu.ee", "lib.ee", "aip.ee")

_LV = ("com.lv", "edu.lv", "gov.lv", "org.lv", "mil.lv", "id.lv", "net.lv",
       "asn.lv", "conf.lv")

_BY = ("gov.by", "mil.by", "com.by", "of.by")

_AT = ("co.at", "or.at", "ac.at", "gv.at", "priv.at")

_FR = ("com.fr", "asso.fr", "nom.fr", "prd.fr", "tm.fr", "gouv.fr",
       "avocat.fr", "aeroport.fr")

_IT = ("gov.it", "edu.it")

_ES = ("com.es", "nom.es", "org.es", "gob.es", "edu.es")

_PT = ("com.pt", "net.pt", "org.pt", "gov.pt", "edu.pt", "int.pt", "publ.pt",
       "nome.pt")

_GR = ("com.gr", "edu.gr", "net.gr", "org.gr", "gov.gr")

_HU = ("co.hu", "org.hu", "gov.hu", "info.hu", "sport.hu", "tm.hu", "priv.hu",
       "news.hu", "film.hu", "media.hu")

_SE = ("org.se", "pp.se", "press.se", "tm.se", "parti.se", "brand.se",
       "komforb.se", "komvux.se", "lanbib.se", "naturbruksgymn.se")

_NO = ("priv.no", "fhs.no", "vgs.no", "fylkesbibl.no", "folkebibl.no",
       "museum.no", "idrett.no", "kommune.no", "herad.no")

_CH_LI = ("gov.ch",)  # both registries are otherwise flat.

_CA = ("on.ca", "qc.ca", "bc.ca", "ab.ca", "mb.ca", "sk.ca", "ns.ca", "nb.ca",
       "nl.ca", "pe.ca", "nt.ca", "nu.ca", "yk.ca", "gc.ca")

_MX = ("com.mx", "net.mx", "org.mx", "gob.mx", "edu.mx")

_BR = ("com.br", "net.br", "org.br", "gov.br", "edu.br", "mil.br", "art.br",
       "blog.br", "jus.br", "leg.br", "mp.br", "rec.br", "tv.br", "eco.br",
       "esp.br", "etc.br", "far.br", "flog.br", "ind.br", "inf.br", "jor.br",
       "radio.br", "srv.br", "tmp.br", "wiki.br")

_AR = ("com.ar", "net.ar", "org.ar", "gov.ar", "gob.ar", "edu.ar", "int.ar",
       "mil.ar", "tur.ar", "musica.ar")

_CO = ("com.co", "net.co", "org.co", "gov.co", "edu.co", "mil.co", "nom.co")

_CL = ("co.cl", "gob.cl", "gov.cl")

_PE = ("com.pe", "net.pe", "org.pe", "gob.pe", "edu.pe", "mil.pe", "nom.pe",
       "sld.pe")

_VE = ("com.ve", "net.ve", "org.ve", "gob.ve", "edu.ve", "mil.ve", "web.ve",
       "info.ve", "co.ve")

_EC = ("com.ec", "net.ec", "org.ec", "gob.ec", "edu.ec", "mil.ec", "fin.ec",
       "info.ec", "pro.ec", "med.ec")

_UY = ("com.uy", "net.uy", "org.uy", "gub.uy", "edu.uy", "mil.uy")

_BO_PY = ("com.bo", "net.bo", "org.bo", "gob.bo", "edu.bo", "gov.bo", "int.bo",
          "mil.bo", "tv.bo",
          "com.py", "net.py", "org.py", "gov.py", "edu.py", "mil.py", "una.py")

_CR_GT = ("co.cr", "ac.cr", "go.cr", "or.cr", "sa.cr", "ed.cr", "fi.cr",
          "com.gt", "net.gt", "org.gt", "gob.gt", "edu.gt", "mil.gt", "ind.gt")

_NG = ("com.ng", "net.ng", "org.ng", "gov.ng", "edu.ng", "sch.ng", "mil.ng",
       "name.ng")

_KE = ("co.ke", "ne.ke", "or.ke", "go.ke", "ac.ke", "sc.ke", "me.ke",
       "mobi.ke", "info.ke")

_GH_TZ_UG = ("com.gh", "edu.gh", "gov.gh", "org.gh", "mil.gh",
             "co.tz", "ac.tz", "go.tz", "or.tz", "ne.tz", "mil.tz", "sc.tz",
             "co.ug", "ac.ug", "sc.ug", "go.ug", "ne.ug", "or.ug", "org.ug",
             "com.ug")

_ET_ZW_ZM = ("com.et", "gov.et", "org.et", "edu.et", "net.et", "biz.et",
             "name.et", "info.et",
             "co.zw", "ac.zw", "org.zw", "gov.zw", "mil.zw",
             "co.zm", "ac.zm", "org.zm", "gov.zm", "sch.zm")

_MA_DZ_TN = ("co.ma", "net.ma", "org.ma", "gov.ma", "ac.ma", "press.ma",
             "com.dz", "net.dz", "org.dz", "gov.dz", "edu.dz", "asso.dz",
             "pol.dz", "art.dz",
             "com.tn", "net.tn", "org.tn", "gov.tn", "ens.tn", "fin.tn",
             "ind.tn", "intl.tn", "nat.tn", "info.tn", "perso.tn",
             "tourism.tn", "edunet.tn", "rnu.tn")

_EG = ("com.eg", "net.eg", "org.eg", "gov.eg", "edu.eg", "eun.eg", "sci.eg",
       "mil.eg", "name.eg", "sport.eg", "tv.eg", "info.eg")

_SA_AE = ("com.sa", "net.sa", "org.sa", "gov.sa", "edu.sa", "med.sa", "pub.sa",
          "sch.sa",
          "co.ae", "net.ae", "org.ae", "gov.ae", "ac.ae", "sch.ae", "mil.ae",
          "pro.ae", "name.ae")

_IR = ("co.ir", "net.ir", "org.ir", "gov.ir", "ac.ir", "sch.ir", "id.ir")

_LEVANT_GULF = ("gov.iq", "edu.iq", "mil.iq", "com.iq", "org.iq", "net.iq",
                "com.jo", "net.jo", "org.jo", "gov.jo", "edu.jo", "mil.jo",
                "sch.jo", "name.jo",
                "com.lb", "net.lb", "org.lb", "gov.lb", "edu.lb",
                "com.sy", "net.sy", "org.sy", "gov.sy", "edu.sy", "mil.sy",
                "news.sy",
                "com.ps", "net.ps", "org.ps", "gov.ps", "edu.ps", "plo.ps",
                "sec.ps",
                "com.qa", "net.qa", "org.qa", "gov.qa", "edu.qa", "mil.qa",
                "sch.qa", "name.qa",
                "com.kw", "net.kw", "org.kw", "gov.kw", "edu.kw", "ind.kw",
                "emb.kw",
                "com.bh", "net.bh", "org.bh", "gov.bh", "edu.bh", "biz.bh",
                "info.bh",
                "com.om", "net.om", "org.om", "gov.om", "edu.om", "ac.om",
                "biz.om", "co.om", "med.om", "pro.om", "sch.om",
                "com.ly", "net.ly", "org.ly", "gov.ly", "plc.ly", "edu.ly",
                "sch.ly", "med.ly", "id.ly")

_MISC = (
    # Generic registries that sell a level down.
    "com.io", "co.io",
    # Widely used commercial second levels under generic TLDs.
    "co.com", "com.de", "com.se",
    # US federal/state-adjacent, the ones a news corpus hits.
    "fed.us", "dni.us", "isa.us", "nsn.us", "kids.us",
)

#: Multi-label registry suffixes. Membership means "names are sold one level
#: below this", so the registrable domain is this plus one more label.
ICANN_SUFFIXES: frozenset[str] = frozenset(
    _UK + _IE + _AU + _NZ + _ZA + _IN + _JP + _KR + _CN + _HK + _TW + _SG
    + _MY + _ID + _PH + _TH + _VN + _PK + _BD + _LK + _NP + _IL + _TR + _RU
    + _UA + _PL + _CZ_SK + _RO + _RS + _HR + _MK + _AL_BA + _ME + _EE + _LV
    + _BY + _AT + _FR + _IT + _ES + _PT + _GR + _HU + _SE + _NO + _CH_LI
    + _CA + _MX + _BR + _AR + _CO + _CL + _PE + _VE + _EC + _UY + _BO_PY
    + _CR_GT + _NG + _KE + _GH_TZ_UG + _ET_ZW_ZM + _MA_DZ_TN + _EG + _SA_AE
    + _IR + _LEVANT_GULF + _MISC
)

#: TLDs where *every* second-level label is a registry suffix — the PSL spells
#: these ``*.bd``, ``*.ck`` and so on. Listed separately because they cannot be
#: enumerated.
#:
#: The PSL's exception rules (``!www.ck`` and a few others) are not implemented.
#: Their absence treats one extra label as a suffix, which understates
#: independence for a handful of hosts no news corpus contains — the safe
#: direction, and the reason this is a documented gap rather than a bug.
WILDCARD_TLDS: frozenset[str] = frozenset(
    {"bd", "ck", "er", "fj", "jm", "kh", "mm", "pg", "ye"}
)

# --------------------------------------------------------------- multi-tenant ----


#: Hosts where each label beneath is a *different party*, so the subdomain is part
#: of the publisher's identity: ``alice.substack.com`` and ``bob.substack.com``
#: are two independent sources, not one.
#:
#: Treated exactly like an :data:`ICANN_SUFFIXES` entry — the mechanics are the
#: same, only the reason differs. The PSL calls these its private section.
#:
#: Judged on the substantive question rather than by list membership, since the
#: list is not readable here: does a reader who trusts ``alice.substack.com``
#: thereby have reason to trust ``bob.substack.com``? Where the answer is no, the
#: host belongs here.
MULTI_TENANT: frozenset[str] = frozenset({
    # Newsletters and blogging platforms, where the subdomain *is* the author.
    "substack.com",
    "wordpress.com",
    "tumblr.com",
    "livejournal.com",
    "typepad.com",
    "dreamwidth.org",
    "ghost.io",
    "micro.blog",
    "bearblog.dev",
    "hashnode.dev",
    "medium.com",
    "beehiiv.com",
    "hatenablog.com",
    "hateblo.jp",
    "exblog.jp",
    "seesaa.net",
    "cocolog-nifty.com",
    "over-blog.com",
    "canalblog.com",
    "skyrock.com",
    # Site builders.
    "wixsite.com",
    "weebly.com",
    "webflow.io",
    "neocities.org",
    "notion.site",
    "framer.website",
    "super.site",
    "carrd.co",
    "mystrikingly.com",
    # Developer hosting. Reachable static sites, one per account or project.
    "github.io",
    "gitlab.io",
    "pages.dev",
    "workers.dev",
    "netlify.app",
    "vercel.app",
    "glitch.me",
    "herokuapp.com",
    "appspot.com",
    "azurewebsites.net",
    "azurestaticapps.net",
    "cloudfunctions.net",
    "surge.sh",
    "fly.dev",
    "onrender.com",
    "railway.app",
    "streamlit.app",
    "readthedocs.io",
    # Blogger, which localises its own domain. Same platform, one entry each,
    # because `x.blogspot.de` and `y.blogspot.de` are two authors just as
    # `x.blogspot.com` and `y.blogspot.com` are.
    "blogspot.com",
    "blogspot.ae",
    "blogspot.al",
    "blogspot.am",
    "blogspot.ba",
    "blogspot.be",
    "blogspot.bg",
    "blogspot.bj",
    "blogspot.ca",
    "blogspot.cat",
    "blogspot.cf",
    "blogspot.ch",
    "blogspot.cl",
    "blogspot.co.at",
    "blogspot.co.id",
    "blogspot.co.il",
    "blogspot.co.ke",
    "blogspot.co.nz",
    "blogspot.co.uk",
    "blogspot.co.za",
    "blogspot.com.ar",
    "blogspot.com.au",
    "blogspot.com.br",
    "blogspot.com.by",
    "blogspot.com.co",
    "blogspot.com.cy",
    "blogspot.com.ee",
    "blogspot.com.eg",
    "blogspot.com.es",
    "blogspot.com.mt",
    "blogspot.com.ng",
    "blogspot.com.pt",
    "blogspot.com.tr",
    "blogspot.com.uy",
    "blogspot.cv",
    "blogspot.cz",
    "blogspot.de",
    "blogspot.dk",
    "blogspot.fi",
    "blogspot.fr",
    "blogspot.gr",
    "blogspot.hk",
    "blogspot.hr",
    "blogspot.hu",
    "blogspot.ie",
    "blogspot.in",
    "blogspot.is",
    "blogspot.it",
    "blogspot.jp",
    "blogspot.kr",
    "blogspot.li",
    "blogspot.lt",
    "blogspot.lu",
    "blogspot.md",
    "blogspot.mk",
    "blogspot.mr",
    "blogspot.mx",
    "blogspot.my",
    "blogspot.nl",
    "blogspot.no",
    "blogspot.pe",
    "blogspot.pt",
    "blogspot.qa",
    "blogspot.re",
    "blogspot.ro",
    "blogspot.rs",
    "blogspot.ru",
    "blogspot.se",
    "blogspot.sg",
    "blogspot.si",
    "blogspot.sk",
    "blogspot.sn",
    "blogspot.td",
    "blogspot.tw",
    "blogspot.ug",
    "blogspot.vn",
})

#: Everything treated as a suffix, whatever the reason. One lookup, because the
#: arithmetic is identical: find the longest match, take one more label.
SUFFIXES: frozenset[str] = ICANN_SUFFIXES | MULTI_TENANT

#: The longest suffix in the table, in labels. Bounds the lookup loop so it tries
#: four candidate lengths rather than walking every label of a long hostname.
MAX_SUFFIX_LABELS: int = max(
    (suffix.count(".") + 1 for suffix in SUFFIXES), default=1
)
