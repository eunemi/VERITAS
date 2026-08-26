"""What kind of publisher a domain is. **Never how truthful it is.**

This is the table :mod:`app.domain.credibility` promises exists, and the promise it
makes about it is the important part: *it grades none of its entries for
truthfulness.* Every value in here is a :class:`~app.domain.credibility.Role`, every
member of that enum is a checkable fact about an institution — who owns it, what
records it holds, whether it writes what it publishes — and the enum has no
``RELIABLE`` member for a scorer to reach for. There is nothing in this module that
says a claim published on any domain is more likely to be true, and no arrangement of
what is here could produce one.

That has to be stated first because a file that maps ``rt.com`` and ``bbc.co.uk`` to
different values looks exactly like a blocklist, and is not one. Both are recognised.
Both get an accountable publisher on :attr:`~app.domain.credibility.Axis.RELIABILITY`,
because both have a masthead and an editorial chain and somebody who answers for the
copy. They differ on :attr:`~app.domain.credibility.Axis.INDEPENDENCE`, which is a
statement about who they answer *to*, and on nothing else. A state broadcaster
reporting what its ministry announced is the authority on what was announced; that is
what the separation of axes is for.

Four tables, and each one is a different kind of claim
-----------------------------------------------------

:data:`PUBLISHERS`
    Named institutions, one :class:`~app.domain.credibility.Role` each. A few hundred
    entries against a web of hundreds of millions, so **a miss is the common case and
    carries no penalty** — see :func:`look_up`. This is the only table a reader is
    likely to want to argue with, which is why it is one flat literal with the reason
    for each section written above it rather than logic spread across a scorer.

:data:`OFFICIAL_SUFFIXES`
    Registry suffixes under which every name belongs to a government or a treaty
    organisation: ``gov``, ``mil``, ``int``, ``gov.uk``, ``gouv.fr``, ``gc.ca``. This
    is a structural fact about who a registry sells to, not a judgement about any
    site, and it is what lets ``bls.gov`` and ``ons.gov.uk`` read as record-holders
    without either of them being listed by name.

:data:`ACADEMIC_SUFFIXES`
    The same idea for the education registries — ``edu``, ``ac.uk``, ``edu.au``. Held
    apart from the official suffixes rather than folded in with them because a
    university holds *its own* research record and not a government's, and a claim
    about what a statute says is not answered by a faculty page.

:data:`OWNERS`
    Which titles are the same company. The one table here whose incompleteness is not
    safe, and :func:`owner` says why at length.

Self-publishing platforms are deliberately **not** a fifth table: :data:`SUFFIXES`'s
:data:`~app.research.suffixes.MULTI_TENANT` already enumerates the hosts where the
subdomain is the author, for the neighbouring purpose of deciding that
``alice.substack.com`` and ``bob.substack.com`` are two publishers. That is the same
set, established for the same reason, and :func:`self_published` reads it rather than
restating it — a second copy would drift, and the drift would be silent.

Why a curated literal at all
----------------------------
Because the alternative is a rating service. There are vendors who will sell a
per-domain trust score, and buying one would move this service's central judgement
behind an API nobody can read, priced by a third party with its own politics, and turn
"is this claim true" into "what does the vendor think of this masthead". Everything in
here is instead a fact a reader can check in an afternoon, written where they can see
it, wrong in ways they can point at.

It decays, and the decay is asymmetric by design
------------------------------------------------
Ownership changes, outlets fold, broadcasters are privatised. Three of the four tables
fail safely under staleness because a stale entry still describes a real institution
and a missing entry only costs coverage — :attr:`~app.domain.credibility.Reading.score`
goes to ``None``, which the domain model treats as an absence of assessment rather
than a finding. :data:`OWNERS` is the exception and is documented as one.
"""

from __future__ import annotations

from app.domain.credibility import Role
from app.research.suffixes import MULTI_TENANT

__all__ = [
    "ACADEMIC_SUFFIXES",
    "OFFICIAL_SUFFIXES",
    "OWNERS",
    "PUBLISHERS",
    "academic_suffix",
    "look_up",
    "official_suffix",
    "owner",
    "self_published",
]


# ============================================================ registry suffixes ====

#: Suffixes under which every registered name belongs to a state or treaty body.
#:
#: Membership is a fact about a registry's eligibility rules, not about any site: the
#: ``.gov`` registry sells only to United States government entities, ``.int`` only to
#: organisations established by international treaty, ``gouv.fr`` only to French
#: government bodies. So a host under one of these *holds the record* in the sense
#: :attr:`~app.domain.credibility.Axis.OFFICIAL` means, and nothing more than that —
#: a ministry's press release is authoritative on what the ministry announced and is
#: not an independent assessment of whether it worked. That caveat is not left to the
#: reader: :mod:`app.research.credibility` attaches it to every source this fires on.
#:
#: The rule for adding an entry is the one :mod:`app.research.suffixes` uses, applied
#: to a different question: an entry goes in only when *every* name beneath it is a
#: government body. ``gov.uk`` qualifies. ``org.uk`` does not, and neither does ``us``
#: or ``eu`` — plenty of private sites sit under both, and a suffix that admitted them
#: would hand the officiality of a statute to anyone who registered a domain.
OFFICIAL_SUFFIXES: frozenset[str] = frozenset({
    # Single-label registries with government or treaty eligibility rules. `.int` is
    # the narrowest registry on the internet: an applicant must be an organisation
    # established by a treaty between states.
    "gov", "mil", "int",
    # United Kingdom. `nhs.uk`, `police.uk` and `mod.uk` are public bodies with their
    # own registries, which is why they are listed beside `gov.uk` rather than left to
    # it.
    "gov.uk", "nhs.uk", "police.uk", "mod.uk", "parliament.uk", "royal.uk",
    "gov.ie", "gov.scot", "gov.wales", "llyw.cymru",
    # Canada, which uses a plain second level rather than a registry suffix.
    "gc.ca", "canada.ca",
    # Europe. `europa.eu` is the Union's own domain and every body sits beneath it —
    # `ec.`, `europarl.`, `curia.`, `eca.` — so the suffix catches them all.
    "europa.eu", "gouv.fr", "gov.it", "gob.es", "gov.pt", "gov.gr", "gv.at",
    "admin.ch", "gov.ch", "gov.pl", "gov.hu", "gov.ee", "riik.ee", "gov.lv",
    "gov.rs", "gov.mk", "gov.al", "gov.ba", "gov.me", "gov.ua", "gov.by",
    "gov.ru", "mil.ru", "bund.de", "overheid.nl", "riksdagen.se", "regjeringen.no",
    # Asia-Pacific.
    "gov.au", "govt.nz", "parliament.nz", "mil.nz", "go.jp", "lg.jp", "go.kr",
    "mil.kr", "gov.cn", "mil.cn", "gov.hk", "gov.tw", "gov.sg", "gov.my",
    "go.id", "mil.id", "gov.ph", "mil.ph", "go.th", "mi.th", "gov.vn",
    "gov.in", "nic.in", "mil.in", "gov.pk", "gob.pk", "gok.pk", "gop.pk",
    "gos.pk", "gov.bd", "gov.lk", "gov.np", "mil.np",
    # Middle East and Africa.
    "gov.il", "muni.il", "gov.tr", "mil.tr", "gov.ae", "gov.sa", "gov.qa",
    "gov.eg", "gov.za", "mil.za", "gov.ng", "mil.ng", "go.ke", "gov.gh",
    "gov.et", "gov.ma", "gov.tn",
    # Latin America. The Spanish-speaking registries mostly use `gob`, and Uruguay
    # uses `gub`; each is that country's government registry and none of them is a
    # variant spelling of another.
    "gob.mx", "gov.br", "mil.br", "gov.ar", "gob.ar", "gob.cl", "gov.cl",
    "gob.pe", "mil.pe", "gov.co", "mil.co", "gob.ve", "mil.ve", "gob.ec",
    "mil.ec", "gub.uy", "mil.uy", "gob.bo", "gov.bo", "go.cr", "gob.gt",
    "gob.pa", "gob.do", "gob.hn", "gob.sv", "gob.ni", "gov.py",
    # Intergovernmental bodies on generic TLDs, where `.int` was never taken. Each is
    # a treaty organisation whose subdomains are all its own.
    "un.org", "unesco.org", "unicef.org", "undp.org", "unhcr.org", "unep.org",
    "fao.org", "ilo.org", "imf.org", "worldbank.org", "wto.org", "oecd.org",
    "who.int", "wipo.int", "icc-cpi.int", "coe.int", "nato.int", "iaea.org",
    "ipcc.ch", "wmo.int", "bis.org", "icao.int", "imo.org", "itu.int",
})

#: Suffixes reserved for degree-granting institutions and research councils.
#:
#: Kept apart from :data:`OFFICIAL_SUFFIXES` because they answer a different question.
#: A university holds the record of its own research and its own announcements; it does
#: not hold the government's record, and a claim about what a statute says is not
#: settled by a faculty page. So this fires a weaker reading on
#: :attr:`~app.domain.credibility.Axis.OFFICIAL` rather than the same one.
#:
#: ``ac.uk`` and ``edu.au`` are here rather than ``.edu`` alone because outside the
#: United States the education registry is a second-level suffix, and reading only
#: ``.edu`` would recognise Harvard and not Oxford.
ACADEMIC_SUFFIXES: frozenset[str] = frozenset({
    "edu",
    "ac.uk", "sch.uk", "ac.nz", "school.nz", "cri.nz", "edu.au", "csiro.au",
    "ac.jp", "ed.jp", "ac.kr", "hs.kr", "ms.kr", "es.kr", "sc.kr", "ac.cn",
    "edu.cn", "edu.hk", "edu.tw", "edu.sg", "edu.my", "ac.id", "sch.id",
    "ac.th", "edu.vn", "ac.vn", "ac.in", "edu.in", "res.in", "edu.pk",
    "ac.bd", "edu.bd", "ac.lk", "sch.lk", "edu.lk", "edu.np",
    "ac.il", "k12.il", "edu.tr", "k12.tr", "ac.za", "edu.za", "ac.ke",
    "sc.ke", "edu.ng", "sch.ng", "ac.ru", "edu.ru", "edu.ua", "edu.pl",
    "edu.ee", "edu.lv", "ac.at", "edu.it", "edu.es", "edu.pt", "edu.gr",
    "ac.me", "edu.me", "edu.rs", "ac.rs", "edu.mk", "edu.al", "edu.ba",
    "edu.mx", "edu.br", "edu.ar", "edu.co", "edu.pe", "edu.ve", "edu.ec",
    "edu.uy", "edu.bo", "ac.cr", "ed.cr",
})


# =================================================================== publishers ====

#: Named institutions and what kind of publisher each one is.
#:
#: Keyed on the **registrable domain** as :func:`app.research.urls.registrable_domain`
#: computes it, because that is the unit of publisher identity everywhere else in this
#: package. Two consequences are worth knowing before reading the table:
#:
#: * A section of a site cannot have its own role. ``factcheck.afp.com`` is AFP's
#:   fact-checking desk and reads as :attr:`Role.NEWS_AGENCY`, because its registrable
#:   domain is ``afp.com``. The loss is real and it is the right trade: the alternative
#:   is a second lookup keyed on the full host, which would let one path of a site
#:   carry a role the rest of it does not and would be wrong far more often than this
#:   is coarse.
#: * A masthead behind a shared corporate domain is invisible here. ABC News lives at
#:   ``abcnews.go.com``, whose registrable domain is Disney's ``go.com``, so it is
#:   absent rather than listed under a key that would also match unrelated Disney
#:   properties. Absent is the honest outcome; see :func:`look_up`.
#:
#: The sections below are the argument. Each one states what the role asserts, so an
#: entry can be checked against the claim being made about it rather than against a
#: reader's impression of the outlet.
PUBLISHERS: dict[str, Role] = {
    # ------------------------------------------------------------------ official ----
    # Holds the record. Almost every government body is caught by
    # `OFFICIAL_SUFFIXES` instead; what is listed here is the bodies on generic or
    # national TLDs that no suffix rule reaches — central banks, statistics agencies
    # and standards bodies that were founded before the registries tidied up.
    "bankofengland.co.uk": Role.OFFICIAL,
    "ecb.europa.eu": Role.OFFICIAL,
    "bundesbank.de": Role.OFFICIAL,
    "banque-france.fr": Role.OFFICIAL,
    "bankofcanada.ca": Role.OFFICIAL,
    "rba.gov.au": Role.OFFICIAL,
    "boj.or.jp": Role.OFFICIAL,
    "snb.ch": Role.OFFICIAL,
    "riksbank.se": Role.OFFICIAL,
    "norges-bank.no": Role.OFFICIAL,
    "rbi.org.in": Role.OFFICIAL,
    "iso.org": Role.OFFICIAL,
    "ietf.org": Role.OFFICIAL,
    "w3.org": Role.OFFICIAL,
    "ieee.org": Role.OFFICIAL,
    "iec.ch": Role.OFFICIAL,
    "icann.org": Role.OFFICIAL,
    "iana.org": Role.OFFICIAL,
    "bipm.org": Role.OFFICIAL,
    "iupac.org": Role.OFFICIAL,
    "redcross.org": Role.OFFICIAL,
    "icrc.org": Role.OFFICIAL,
    "olympics.com": Role.OFFICIAL,
    "fifa.com": Role.OFFICIAL,
    "uefa.com": Role.OFFICIAL,
    "wada-ama.org": Role.OFFICIAL,
    "ema.europa.eu": Role.OFFICIAL,
    "efsa.europa.eu": Role.OFFICIAL,
    "eba.europa.eu": Role.OFFICIAL,
    "esma.europa.eu": Role.OFFICIAL,
    "cern": Role.OFFICIAL,
    "home.cern": Role.OFFICIAL,
    "esa.int": Role.OFFICIAL,
    "eumetsat.int": Role.OFFICIAL,
    "copernicus.eu": Role.OFFICIAL,
    "metoffice.gov.uk": Role.OFFICIAL,
    "ons.gov.uk": Role.OFFICIAL,
    # ----------------------------------------------------------------- reference ----
    # A repository of primary documents it did not itself author. The role says the
    # documents are there to be read, not that any of them is correct: a preprint
    # server is a reference precisely because it publishes what has *not* been
    # reviewed, and a filings archive holds whatever the filer said.
    "arxiv.org": Role.REFERENCE,
    "biorxiv.org": Role.REFERENCE,
    "medrxiv.org": Role.REFERENCE,
    "ssrn.com": Role.REFERENCE,
    "zenodo.org": Role.REFERENCE,
    "osf.io": Role.REFERENCE,
    "doi.org": Role.REFERENCE,
    "crossref.org": Role.REFERENCE,
    "orcid.org": Role.REFERENCE,
    "archive.org": Role.REFERENCE,
    "hathitrust.org": Role.REFERENCE,
    "jstor.org": Role.REFERENCE,
    "gutenberg.org": Role.REFERENCE,
    "courtlistener.com": Role.REFERENCE,
    "documentcloud.org": Role.REFERENCE,
    "govtrack.us": Role.REFERENCE,
    "opensecrets.org": Role.REFERENCE,
    "followthemoney.org": Role.REFERENCE,
    "ourworldindata.org": Role.REFERENCE,
    "cochranelibrary.com": Role.REFERENCE,
    "clinicaltrials.gov": Role.REFERENCE,
    "sciencedirect.com": Role.REFERENCE,
    "springer.com": Role.REFERENCE,
    "wiley.com": Role.REFERENCE,
    "tandfonline.com": Role.REFERENCE,
    "sagepub.com": Role.REFERENCE,
    "plos.org": Role.REFERENCE,
    "biomedcentral.com": Role.REFERENCE,
    "frontiersin.org": Role.REFERENCE,
    "mdpi.com": Role.REFERENCE,
    "pnas.org": Role.REFERENCE,
    "bmj.com": Role.REFERENCE,
    "nejm.org": Role.REFERENCE,
    "thelancet.com": Role.REFERENCE,
    "jamanetwork.com": Role.REFERENCE,
    "cell.com": Role.REFERENCE,
    "acs.org": Role.REFERENCE,
    "aps.org": Role.REFERENCE,
    "rsc.org": Role.REFERENCE,
    "iopscience.iop.org": Role.REFERENCE,
    "royalsociety.org": Role.REFERENCE,
    "nationalarchives.gov.uk": Role.REFERENCE,
    "loc.gov": Role.REFERENCE,
    "bl.uk": Role.REFERENCE,
    # --------------------------------------------------------------- news agency ----
    # Original reporting, and the origin of most syndication. The role matters on
    # `Axis.INDEPENDENCE` in both directions: an agency is a distinct voice, and it is
    # the voice the eight regional mastheads carrying its copy are *not*.
    "reuters.com": Role.NEWS_AGENCY,
    "apnews.com": Role.NEWS_AGENCY,
    "afp.com": Role.NEWS_AGENCY,
    "bloomberg.com": Role.NEWS_AGENCY,
    "pa.media": Role.NEWS_AGENCY,
    "dpa.com": Role.NEWS_AGENCY,
    "efe.com": Role.NEWS_AGENCY,
    "ansa.it": Role.NEWS_AGENCY,
    "belga.be": Role.NEWS_AGENCY,
    "kyodonews.net": Role.NEWS_AGENCY,
    "jiji.com": Role.NEWS_AGENCY,
    "yonhapnews.co.kr": Role.NEWS_AGENCY,
    "ptinews.com": Role.NEWS_AGENCY,
    "aninews.in": Role.NEWS_AGENCY,
    "ians.in": Role.NEWS_AGENCY,
    "interfax.com": Role.NEWS_AGENCY,
    "notimex.com.mx": Role.NEWS_AGENCY,
    "aap.com.au": Role.NEWS_AGENCY,
    # ----------------------------------------------------------- established media ----
    # A masthead with an editorial chain and a corrections process. That is the whole
    # assertion, and it is what `Axis.RELIABILITY` measures: somebody is accountable
    # for the copy. It is emphatically not a record of being right — this service has
    # no way to measure that, and any number claiming to would be invented.
    #
    # Public broadcasters with statutory editorial independence are here rather than
    # under `STATE_CONTROLLED`, and the line is *who the editor answers to*, not who
    # pays. The BBC is funded by a licence fee and constituted by a charter that puts
    # editorial control beyond ministerial reach; so are ARD, ZDF, France Télévisions,
    # NPR, PBS, CBC, ABC Australia and NHK. A broadcaster whose editor is appointed by
    # and removable by a ministry is a different institution and is listed as one.
    "bbc.co.uk": Role.ESTABLISHED_MEDIA,
    "bbc.com": Role.ESTABLISHED_MEDIA,
    "theguardian.com": Role.ESTABLISHED_MEDIA,
    "nytimes.com": Role.ESTABLISHED_MEDIA,
    "washingtonpost.com": Role.ESTABLISHED_MEDIA,
    "wsj.com": Role.ESTABLISHED_MEDIA,
    "ft.com": Role.ESTABLISHED_MEDIA,
    "economist.com": Role.ESTABLISHED_MEDIA,
    "telegraph.co.uk": Role.ESTABLISHED_MEDIA,
    "thetimes.co.uk": Role.ESTABLISHED_MEDIA,
    "independent.co.uk": Role.ESTABLISHED_MEDIA,
    "standard.co.uk": Role.ESTABLISHED_MEDIA,
    "inews.co.uk": Role.ESTABLISHED_MEDIA,
    "observer.co.uk": Role.ESTABLISHED_MEDIA,
    "dailymail.co.uk": Role.ESTABLISHED_MEDIA,
    "mirror.co.uk": Role.ESTABLISHED_MEDIA,
    "express.co.uk": Role.ESTABLISHED_MEDIA,
    "thesun.co.uk": Role.ESTABLISHED_MEDIA,
    "metro.co.uk": Role.ESTABLISHED_MEDIA,
    "channel4.com": Role.ESTABLISHED_MEDIA,
    "itv.com": Role.ESTABLISHED_MEDIA,
    "sky.com": Role.ESTABLISHED_MEDIA,
    "news.sky.com": Role.ESTABLISHED_MEDIA,
    "spectator.co.uk": Role.ESTABLISHED_MEDIA,
    "newstatesman.com": Role.ESTABLISHED_MEDIA,
    "prospectmagazine.co.uk": Role.ESTABLISHED_MEDIA,
    "latimes.com": Role.ESTABLISHED_MEDIA,
    "chicagotribune.com": Role.ESTABLISHED_MEDIA,
    "bostonglobe.com": Role.ESTABLISHED_MEDIA,
    "sfchronicle.com": Role.ESTABLISHED_MEDIA,
    "houstonchronicle.com": Role.ESTABLISHED_MEDIA,
    "dallasnews.com": Role.ESTABLISHED_MEDIA,
    "seattletimes.com": Role.ESTABLISHED_MEDIA,
    "startribune.com": Role.ESTABLISHED_MEDIA,
    "inquirer.com": Role.ESTABLISHED_MEDIA,
    "ajc.com": Role.ESTABLISHED_MEDIA,
    "miamiherald.com": Role.ESTABLISHED_MEDIA,
    "usatoday.com": Role.ESTABLISHED_MEDIA,
    "npr.org": Role.ESTABLISHED_MEDIA,
    "pbs.org": Role.ESTABLISHED_MEDIA,
    "cnn.com": Role.ESTABLISHED_MEDIA,
    "nbcnews.com": Role.ESTABLISHED_MEDIA,
    "cbsnews.com": Role.ESTABLISHED_MEDIA,
    "msnbc.com": Role.ESTABLISHED_MEDIA,
    "foxnews.com": Role.ESTABLISHED_MEDIA,
    "cnbc.com": Role.ESTABLISHED_MEDIA,
    "politico.com": Role.ESTABLISHED_MEDIA,
    "axios.com": Role.ESTABLISHED_MEDIA,
    "thehill.com": Role.ESTABLISHED_MEDIA,
    "propublica.org": Role.ESTABLISHED_MEDIA,
    "theatlantic.com": Role.ESTABLISHED_MEDIA,
    "newyorker.com": Role.ESTABLISHED_MEDIA,
    "time.com": Role.ESTABLISHED_MEDIA,
    "newsweek.com": Role.ESTABLISHED_MEDIA,
    "vox.com": Role.ESTABLISHED_MEDIA,
    "theverge.com": Role.ESTABLISHED_MEDIA,
    "arstechnica.com": Role.ESTABLISHED_MEDIA,
    "wired.com": Role.ESTABLISHED_MEDIA,
    "businessinsider.com": Role.ESTABLISHED_MEDIA,
    "forbes.com": Role.ESTABLISHED_MEDIA,
    "fortune.com": Role.ESTABLISHED_MEDIA,
    "barrons.com": Role.ESTABLISHED_MEDIA,
    "marketwatch.com": Role.ESTABLISHED_MEDIA,
    "nypost.com": Role.ESTABLISHED_MEDIA,
    "nydailynews.com": Role.ESTABLISHED_MEDIA,
    "texastribune.org": Role.ESTABLISHED_MEDIA,
    "themarshallproject.org": Role.ESTABLISHED_MEDIA,
    "revealnews.org": Role.ESTABLISHED_MEDIA,
    "icij.org": Role.ESTABLISHED_MEDIA,
    "bellingcat.com": Role.ESTABLISHED_MEDIA,
    "nature.com": Role.ESTABLISHED_MEDIA,
    "science.org": Role.ESTABLISHED_MEDIA,
    "scientificamerican.com": Role.ESTABLISHED_MEDIA,
    "newscientist.com": Role.ESTABLISHED_MEDIA,
    "sciencenews.org": Role.ESTABLISHED_MEDIA,
    "statnews.com": Role.ESTABLISHED_MEDIA,
    "spiegel.de": Role.ESTABLISHED_MEDIA,
    "zeit.de": Role.ESTABLISHED_MEDIA,
    "faz.net": Role.ESTABLISHED_MEDIA,
    "sueddeutsche.de": Role.ESTABLISHED_MEDIA,
    "welt.de": Role.ESTABLISHED_MEDIA,
    "taz.de": Role.ESTABLISHED_MEDIA,
    "ard.de": Role.ESTABLISHED_MEDIA,
    "zdf.de": Role.ESTABLISHED_MEDIA,
    "tagesschau.de": Role.ESTABLISHED_MEDIA,
    "dw.com": Role.ESTABLISHED_MEDIA,
    "lemonde.fr": Role.ESTABLISHED_MEDIA,
    "lefigaro.fr": Role.ESTABLISHED_MEDIA,
    "liberation.fr": Role.ESTABLISHED_MEDIA,
    "mediapart.fr": Role.ESTABLISHED_MEDIA,
    "francetvinfo.fr": Role.ESTABLISHED_MEDIA,
    "rfi.fr": Role.ESTABLISHED_MEDIA,
    "elpais.com": Role.ESTABLISHED_MEDIA,
    "elmundo.es": Role.ESTABLISHED_MEDIA,
    "eldiario.es": Role.ESTABLISHED_MEDIA,
    "rtve.es": Role.ESTABLISHED_MEDIA,
    "corriere.it": Role.ESTABLISHED_MEDIA,
    "repubblica.it": Role.ESTABLISHED_MEDIA,
    "ilsole24ore.com": Role.ESTABLISHED_MEDIA,
    "rai.it": Role.ESTABLISHED_MEDIA,
    "nrc.nl": Role.ESTABLISHED_MEDIA,
    "volkskrant.nl": Role.ESTABLISHED_MEDIA,
    "nos.nl": Role.ESTABLISHED_MEDIA,
    "dn.se": Role.ESTABLISHED_MEDIA,
    "svt.se": Role.ESTABLISHED_MEDIA,
    "nrk.no": Role.ESTABLISHED_MEDIA,
    "aftenposten.no": Role.ESTABLISHED_MEDIA,
    "dr.dk": Role.ESTABLISHED_MEDIA,
    "politiken.dk": Role.ESTABLISHED_MEDIA,
    "yle.fi": Role.ESTABLISHED_MEDIA,
    "hs.fi": Role.ESTABLISHED_MEDIA,
    "irishtimes.com": Role.ESTABLISHED_MEDIA,
    "rte.ie": Role.ESTABLISHED_MEDIA,
    "swissinfo.ch": Role.ESTABLISHED_MEDIA,
    "nzz.ch": Role.ESTABLISHED_MEDIA,
    "derstandard.at": Role.ESTABLISHED_MEDIA,
    "orf.at": Role.ESTABLISHED_MEDIA,
    "politico.eu": Role.ESTABLISHED_MEDIA,
    "euronews.com": Role.ESTABLISHED_MEDIA,
    "euobserver.com": Role.ESTABLISHED_MEDIA,
    "cbc.ca": Role.ESTABLISHED_MEDIA,
    "globeandmail.com": Role.ESTABLISHED_MEDIA,
    "thestar.com": Role.ESTABLISHED_MEDIA,
    "nationalpost.com": Role.ESTABLISHED_MEDIA,
    "abc.net.au": Role.ESTABLISHED_MEDIA,
    "smh.com.au": Role.ESTABLISHED_MEDIA,
    "theage.com.au": Role.ESTABLISHED_MEDIA,
    "afr.com": Role.ESTABLISHED_MEDIA,
    "theaustralian.com.au": Role.ESTABLISHED_MEDIA,
    "news.com.au": Role.ESTABLISHED_MEDIA,
    "sbs.com.au": Role.ESTABLISHED_MEDIA,
    "crikey.com.au": Role.ESTABLISHED_MEDIA,
    "nzherald.co.nz": Role.ESTABLISHED_MEDIA,
    "stuff.co.nz": Role.ESTABLISHED_MEDIA,
    "rnz.co.nz": Role.ESTABLISHED_MEDIA,
    "thehindu.com": Role.ESTABLISHED_MEDIA,
    "indianexpress.com": Role.ESTABLISHED_MEDIA,
    "indiatimes.com": Role.ESTABLISHED_MEDIA,
    "hindustantimes.com": Role.ESTABLISHED_MEDIA,
    "thewire.in": Role.ESTABLISHED_MEDIA,
    "scroll.in": Role.ESTABLISHED_MEDIA,
    "ndtv.com": Role.ESTABLISHED_MEDIA,
    "dawn.com": Role.ESTABLISHED_MEDIA,
    "thedailystar.net": Role.ESTABLISHED_MEDIA,
    "japantimes.co.jp": Role.ESTABLISHED_MEDIA,
    "asahi.com": Role.ESTABLISHED_MEDIA,
    "yomiuri.co.jp": Role.ESTABLISHED_MEDIA,
    "nikkei.com": Role.ESTABLISHED_MEDIA,
    "nhk.or.jp": Role.ESTABLISHED_MEDIA,
    "koreaherald.com": Role.ESTABLISHED_MEDIA,
    "koreatimes.co.kr": Role.ESTABLISHED_MEDIA,
    "scmp.com": Role.ESTABLISHED_MEDIA,
    "hkfp.com": Role.ESTABLISHED_MEDIA,
    "taipeitimes.com": Role.ESTABLISHED_MEDIA,
    "straitstimes.com": Role.ESTABLISHED_MEDIA,
    "channelnewsasia.com": Role.ESTABLISHED_MEDIA,
    "bangkokpost.com": Role.ESTABLISHED_MEDIA,
    "jakartapost.com": Role.ESTABLISHED_MEDIA,
    "inquirer.net": Role.ESTABLISHED_MEDIA,
    "rappler.com": Role.ESTABLISHED_MEDIA,
    "aljazeera.com": Role.ESTABLISHED_MEDIA,
    "haaretz.com": Role.ESTABLISHED_MEDIA,
    "timesofisrael.com": Role.ESTABLISHED_MEDIA,
    "jpost.com": Role.ESTABLISHED_MEDIA,
    "thenationalnews.com": Role.ESTABLISHED_MEDIA,
    "arabnews.com": Role.ESTABLISHED_MEDIA,
    "middleeasteye.net": Role.ESTABLISHED_MEDIA,
    "mg.co.za": Role.ESTABLISHED_MEDIA,
    "news24.com": Role.ESTABLISHED_MEDIA,
    "dailymaverick.co.za": Role.ESTABLISHED_MEDIA,
    "premiumtimesng.com": Role.ESTABLISHED_MEDIA,
    "nation.africa": Role.ESTABLISHED_MEDIA,
    "theeastafrican.co.ke": Role.ESTABLISHED_MEDIA,
    "folha.uol.com.br": Role.ESTABLISHED_MEDIA,
    "globo.com": Role.ESTABLISHED_MEDIA,
    "estadao.com.br": Role.ESTABLISHED_MEDIA,
    "clarin.com": Role.ESTABLISHED_MEDIA,
    "lanacion.com.ar": Role.ESTABLISHED_MEDIA,
    "eluniversal.com.mx": Role.ESTABLISHED_MEDIA,
    "reforma.com": Role.ESTABLISHED_MEDIA,
    "eltiempo.com": Role.ESTABLISHED_MEDIA,
    "emol.com": Role.ESTABLISHED_MEDIA,
    "elcomercio.pe": Role.ESTABLISHED_MEDIA,
    "meduza.io": Role.ESTABLISHED_MEDIA,
    "novayagazeta.eu": Role.ESTABLISHED_MEDIA,
    "kyivindependent.com": Role.ESTABLISHED_MEDIA,
    "pravda.com.ua": Role.ESTABLISHED_MEDIA,
    # -------------------------------------------------------------- fact checker ----
    # An organisation whose published work is fact-checking. **Noted, not
    # privileged.** A fact-checker is a source like any other, which is the premise of
    # `app.domain.factcheck`: their verdict travels as evidence beside the web sources
    # and is never summed into a rating for the claim. This role earns exactly what
    # `ESTABLISHED_MEDIA` earns on every axis. It is recorded because a reader wants to
    # know they are looking at a review rather than a report, not because it wins.
    #
    # Conspicuously absent: the outlets that rate *other outlets* for bias or
    # reliability. Their product is the per-domain trust score this whole module
    # refuses to produce, and listing them would smuggle it in by the back door.
    "snopes.com": Role.FACT_CHECKER,
    "politifact.com": Role.FACT_CHECKER,
    "factcheck.org": Role.FACT_CHECKER,
    "fullfact.org": Role.FACT_CHECKER,
    "africacheck.org": Role.FACT_CHECKER,
    "chequeado.com": Role.FACT_CHECKER,
    "maldita.es": Role.FACT_CHECKER,
    "newtral.es": Role.FACT_CHECKER,
    "correctiv.org": Role.FACT_CHECKER,
    "faktacheck.de": Role.FACT_CHECKER,
    "faktisk.no": Role.FACT_CHECKER,
    "pagellapolitica.it": Role.FACT_CHECKER,
    "factcheckni.org": Role.FACT_CHECKER,
    "leadstories.com": Role.FACT_CHECKER,
    "checkyourfact.com": Role.FACT_CHECKER,
    "truthorfiction.com": Role.FACT_CHECKER,
    "altnews.in": Role.FACT_CHECKER,
    "boomlive.in": Role.FACT_CHECKER,
    "factly.in": Role.FACT_CHECKER,
    "vishvasnews.com": Role.FACT_CHECKER,
    "tfc-taiwan.org.tw": Role.FACT_CHECKER,
    "stopfake.org": Role.FACT_CHECKER,
    "emergent.info": Role.FACT_CHECKER,
    "climatefeedback.org": Role.FACT_CHECKER,
    "healthfeedback.org": Role.FACT_CHECKER,
    "sciencefeedback.co": Role.FACT_CHECKER,
    # ----------------------------------------------------------- state controlled ----
    # Editorially answerable to a government. This **lowers
    # `Axis.INDEPENDENCE` and nothing else** — see the `Role` docstring, which spells
    # out why that is not a truth finding: a ministry's broadcaster is the authority on
    # what the ministry announced and is not an independent judge of whether it worked.
    # Accountability is untouched: these are real newsrooms with real mastheads, and
    # `Axis.RELIABILITY` reads them as such.
    #
    # The line is who appoints and can remove the editor, applied without regard to
    # whose government it is. That is why `voanews.com` and `rferl.org` are here
    # alongside `rt.com` and `cgtn.com`: the United States Agency for Global Media is a
    # federal agency, and a statutory firewall is a constraint on interference rather
    # than the absence of the relationship. Listing one country's state broadcasters
    # and not another's would be the bias this module exists to keep out — and the
    # entry costs these outlets nothing on any axis except the one it is actually
    # about.
    "rt.com": Role.STATE_CONTROLLED,
    "sputniknews.com": Role.STATE_CONTROLLED,
    "sputnikglobe.com": Role.STATE_CONTROLLED,
    "tass.com": Role.STATE_CONTROLLED,
    "ria.ru": Role.STATE_CONTROLLED,
    "rg.ru": Role.STATE_CONTROLLED,
    "1tv.ru": Role.STATE_CONTROLLED,
    "xinhuanet.com": Role.STATE_CONTROLLED,
    "news.cn": Role.STATE_CONTROLLED,
    "chinadaily.com.cn": Role.STATE_CONTROLLED,
    "globaltimes.cn": Role.STATE_CONTROLLED,
    "cgtn.com": Role.STATE_CONTROLLED,
    "people.com.cn": Role.STATE_CONTROLLED,
    "cctv.com": Role.STATE_CONTROLLED,
    "presstv.ir": Role.STATE_CONTROLLED,
    "irna.ir": Role.STATE_CONTROLLED,
    "tasnimnews.com": Role.STATE_CONTROLLED,
    "kcna.kp": Role.STATE_CONTROLLED,
    "aa.com.tr": Role.STATE_CONTROLLED,
    "trtworld.com": Role.STATE_CONTROLLED,
    "prensa-latina.cu": Role.STATE_CONTROLLED,
    "granma.cu": Role.STATE_CONTROLLED,
    "telesurenglish.net": Role.STATE_CONTROLLED,
    "voanews.com": Role.STATE_CONTROLLED,
    "rferl.org": Role.STATE_CONTROLLED,
    "bbg.gov": Role.STATE_CONTROLLED,
    "wam.ae": Role.STATE_CONTROLLED,
    "spa.gov.sa": Role.STATE_CONTROLLED,
    "saudigazette.com.sa": Role.STATE_CONTROLLED,
    "ahram.org.eg": Role.STATE_CONTROLLED,
    "vietnamnews.vn": Role.STATE_CONTROLLED,
    "nhandan.vn": Role.STATE_CONTROLLED,
    "bernama.com": Role.STATE_CONTROLLED,
    "antaranews.com": Role.STATE_CONTROLLED,
    "belta.by": Role.STATE_CONTROLLED,
    "azertag.az": Role.STATE_CONTROLLED,
    # ---------------------------------------------------------------- aggregator ----
    # Republishes other publishers' work. Lowers `Axis.INDEPENDENCE` because a reprint
    # is not a second witness — and only that: an aggregator has a masthead and is
    # accountable for what it chooses to carry, so accountability is untouched.
    "msn.com": Role.AGGREGATOR,
    "yahoo.com": Role.AGGREGATOR,
    "news.google.com": Role.AGGREGATOR,
    "flipboard.com": Role.AGGREGATOR,
    "smartnews.com": Role.AGGREGATOR,
    "newsbreak.com": Role.AGGREGATOR,
    "realclearpolitics.com": Role.AGGREGATOR,
    "drudgereport.com": Role.AGGREGATOR,
    "memeorandum.com": Role.AGGREGATOR,
    "allsides.com": Role.AGGREGATOR,
    "ground.news": Role.AGGREGATOR,
    "prnewswire.com": Role.AGGREGATOR,
    "businesswire.com": Role.AGGREGATOR,
    "globenewswire.com": Role.AGGREGATOR,
    "eurekalert.org": Role.AGGREGATOR,
    "phys.org": Role.AGGREGATOR,
    "sciencedaily.com": Role.AGGREGATOR,
    "medicalxpress.com": Role.AGGREGATOR,
    "yourstory.com": Role.AGGREGATOR,
    "zerohedge.com": Role.AGGREGATOR,
    # -------------------------------------------------------------- user generated ----
    # The host did not write it and does not vouch for it. Lowers
    # `Axis.RELIABILITY` **only**, because nobody is accountable for the text — not
    # because the text is wrong. The `Role` docstring makes the point that matters
    # here: the most valuable source in a dossier is sometimes an eyewitness with no
    # masthead behind them, and this role has to leave room for that. It does: every
    # other axis is untouched, and a first-hand post carrying the claim's own figure
    # still earns `Axis.EVIDENCE` in full.
    #
    # Wikipedia is here, and it is the entry most likely to be argued with. The
    # assertion is narrow and true: the Wikimedia Foundation does not write the
    # articles and does not vouch for them. That says nothing about the quality of any
    # article, and the citations at the bottom of a good one are exactly the primary
    # sources this service would rather be reading anyway.
    "reddit.com": Role.USER_GENERATED,
    "x.com": Role.USER_GENERATED,
    "twitter.com": Role.USER_GENERATED,
    "facebook.com": Role.USER_GENERATED,
    "instagram.com": Role.USER_GENERATED,
    "threads.net": Role.USER_GENERATED,
    "bsky.app": Role.USER_GENERATED,
    "tiktok.com": Role.USER_GENERATED,
    "youtube.com": Role.USER_GENERATED,
    "youtu.be": Role.USER_GENERATED,
    "rumble.com": Role.USER_GENERATED,
    "odysee.com": Role.USER_GENERATED,
    "vimeo.com": Role.USER_GENERATED,
    "twitch.tv": Role.USER_GENERATED,
    "linkedin.com": Role.USER_GENERATED,
    "quora.com": Role.USER_GENERATED,
    "stackexchange.com": Role.USER_GENERATED,
    "stackoverflow.com": Role.USER_GENERATED,
    "wikipedia.org": Role.USER_GENERATED,
    "wikimedia.org": Role.USER_GENERATED,
    "wiktionary.org": Role.USER_GENERATED,
    "wikidata.org": Role.USER_GENERATED,
    "fandom.com": Role.USER_GENERATED,
    "wikihow.com": Role.USER_GENERATED,
    "medium.com": Role.USER_GENERATED,
    "substack.com": Role.USER_GENERATED,
    "tumblr.com": Role.USER_GENERATED,
    "wordpress.com": Role.USER_GENERATED,
    "blogspot.com": Role.USER_GENERATED,
    "mastodon.social": Role.USER_GENERATED,
    "telegram.org": Role.USER_GENERATED,
    "t.me": Role.USER_GENERATED,
    "vk.com": Role.USER_GENERATED,
    "weibo.com": Role.USER_GENERATED,
    "4chan.org": Role.USER_GENERATED,
    "scribd.com": Role.USER_GENERATED,
    "slideshare.net": Role.USER_GENERATED,
    "academia.edu": Role.USER_GENERATED,
    "researchgate.net": Role.USER_GENERATED,
    "change.org": Role.USER_GENERATED,
    "gofundme.com": Role.USER_GENERATED,
    "patreon.com": Role.USER_GENERATED,
    "github.com": Role.USER_GENERATED,
    "gitlab.com": Role.USER_GENERATED,
    "discord.com": Role.USER_GENERATED,
    "imgur.com": Role.USER_GENERATED,
    "pinterest.com": Role.USER_GENERATED,
    "nextdoor.com": Role.USER_GENERATED,
}


# ======================================================================= owners ====

#: Which titles are the same company, as a domain-to-owner map.
#:
#: Read by :mod:`app.research.credibility` for one purpose: two sources under one
#: owner are not two independent voices, however different their mastheads look, and
#: :attr:`~app.domain.credibility.Axis.INDEPENDENCE` is the axis that has to know.
#: Syndication clustering already catches the case where two titles run the *same
#: copy*; this catches the case where a group's titles cover one story separately and
#: a reader counts three publishers where there is one newsroom budget.
#:
#: **This is the one table here whose incompleteness is not the safe direction**, and
#: the asymmetry is worth being explicit about because it is the reverse of
#: :mod:`app.research.suffixes`. A *missing* entry lets two siblings read as
#: independent, which overstates corroboration — the error this service is built to
#: avoid. A *wrong* entry lowers a genuinely independent publisher's independence,
#: which understates it and, worse, publishes a finding about a publisher that is not
#: true.
#:
#: Neither error is acceptable and there is no setting of the table that avoids both,
#: so the exposure is bounded structurally instead:
#:
#: * The reading is reported *beside* the sources and never applied to them. Nothing
#:   here reorders a dossier, drops a source or changes what a desk sees — so a wrong
#:   entry costs a number in a response that also shows the domains it was computed
#:   from, and a reader who disagrees can see the disagreement.
#: * The sibling finding **lowers** one axis of six rather than vetoing anything, and
#:   :data:`~app.domain.credibility.MIN_AXES` means it can never be what decides a
#:   band on its own.
#: * Entries are group memberships of public record, and the ones that change are the
#:   ones to check first: this table needs re-reading when a group is broken up, and a
#:   stale entry survives here longer than anywhere else in the package.
#:
#: The owner value is an opaque slug. It is never published — only the fact that two
#: domains matched — because naming a corporate parent in a response would be an
#: assertion about a company that this table is not careful enough to make.
OWNERS: dict[str, str] = {
    # News UK / News Corp UK.
    "thetimes.co.uk": "news-corp",
    "thesun.co.uk": "news-corp",
    # News Corp US.
    "wsj.com": "news-corp",
    "nypost.com": "news-corp",
    "barrons.com": "news-corp",
    "marketwatch.com": "news-corp",
    # News Corp Australia.
    "news.com.au": "news-corp",
    "theaustralian.com.au": "news-corp",
    # DMG Media.
    "dailymail.co.uk": "dmg",
    "thisismoney.co.uk": "dmg",
    "metro.co.uk": "dmg",
    "inews.co.uk": "dmg",
    # Reach plc.
    "mirror.co.uk": "reach",
    "express.co.uk": "reach",
    "dailystar.co.uk": "reach",
    "walesonline.co.uk": "reach",
    "liverpoolecho.co.uk": "reach",
    "manchestereveningnews.co.uk": "reach",
    "birminghammail.co.uk": "reach",
    # Nine Entertainment.
    "smh.com.au": "nine",
    "theage.com.au": "nine",
    "afr.com": "nine",
    # Comcast / NBCUniversal.
    "nbcnews.com": "comcast",
    "msnbc.com": "comcast",
    "cnbc.com": "comcast",
    "today.com": "comcast",
    # Condé Nast.
    "newyorker.com": "conde-nast",
    "wired.com": "conde-nast",
    "vanityfair.com": "conde-nast",
    "arstechnica.com": "conde-nast",
    # Vox Media.
    "vox.com": "vox-media",
    "theverge.com": "vox-media",
    "polygon.com": "vox-media",
    "sbnation.com": "vox-media",
    # Hearst.
    "sfchronicle.com": "hearst",
    "houstonchronicle.com": "hearst",
    "timesunion.com": "hearst",
    "esquire.com": "hearst",
    "cosmopolitan.com": "hearst",
    # Alden Global Capital: Tribune Publishing and MediaNews Group.
    "chicagotribune.com": "alden",
    "nydailynews.com": "alden",
    "baltimoresun.com": "alden",
    "orlandosentinel.com": "alden",
    "courant.com": "alden",
    "denverpost.com": "alden",
    "mercurynews.com": "alden",
    "ocregister.com": "alden",
    "bostonherald.com": "alden",
    # Springer Nature. `nature.com` and `scientificamerican.com` look like two
    # independent voices on a science claim and are one publisher.
    "nature.com": "springer-nature",
    "scientificamerican.com": "springer-nature",
    "springer.com": "springer-nature",
    "biomedcentral.com": "springer-nature",
    # RELX / Elsevier.
    "sciencedirect.com": "elsevier",
    "thelancet.com": "elsevier",
    "cell.com": "elsevier",
    "ssrn.com": "elsevier",
    # Rossiya Segodnya and the wider Russian state media group.
    "rt.com": "russia-state",
    "sputniknews.com": "russia-state",
    "sputnikglobe.com": "russia-state",
    "ria.ru": "russia-state",
    "tass.com": "russia-state",
    "rg.ru": "russia-state",
    # Chinese state media.
    "xinhuanet.com": "china-state",
    "news.cn": "china-state",
    "chinadaily.com.cn": "china-state",
    "globaltimes.cn": "china-state",
    "cgtn.com": "china-state",
    "people.com.cn": "china-state",
    "cctv.com": "china-state",
    # United States Agency for Global Media.
    "voanews.com": "usagm",
    "rferl.org": "usagm",
    # Paramount / CBS.
    "cbsnews.com": "paramount",
    # Warner Bros. Discovery.
    "cnn.com": "wbd",
    # Axel Springer.
    "politico.com": "axel-springer",
    "politico.eu": "axel-springer",
    "businessinsider.com": "axel-springer",
    "welt.de": "axel-springer",
    # Guardian Media Group.
    "theguardian.com": "gmg",
    "observer.co.uk": "gmg",
    # Nikkei, which owns the FT.
    "ft.com": "nikkei",
    "nikkei.com": "nikkei",
}


# ====================================================================== lookups ====


def look_up(domain: str) -> Role | None:
    """What kind of publisher ``domain`` is, or ``None`` when nothing is known.

    ``None`` is the **common case** and carries no penalty of its own. The table is a
    few hundred domains and the web is not, so an unrecognised publisher is assessed
    on what can be seen about the page — its date, whether a passage bears on the
    claim, whether it is a reprint of the source beside it — and that is how a
    first-hand account from an outlet nobody has heard of stays readable as evidence.
    A caller that renders a miss as a negative finding has turned an absence of
    information into a judgement about a publisher.

    Matched on the registrable domain exactly, with no walking up the labels: a
    subdomain cannot inherit a parent's role, because the parent's role was decided
    about the parent. Case and a trailing dot are the only normalisation, and they are
    applied because a provider's URL is not guaranteed to have been through
    :func:`app.research.urls.registrable_domain` first.
    """
    return PUBLISHERS.get(_key(domain))


def official_suffix(host: str) -> str | None:
    """The government or treaty registry suffix ``host`` sits under, or ``None``.

    Returns the matched suffix rather than a boolean so the observation can name it:
    "under the ``gov.uk`` registry" is checkable by a reader and "official" is not.

    Longest match wins, which matters for the handful of entries that nest — ``gov.uk``
    inside ``uk``, ``ecb.europa.eu`` inside ``europa.eu`` — so the most specific true
    statement is the one reported.
    """
    return _longest_suffix(host, OFFICIAL_SUFFIXES)


def academic_suffix(host: str) -> str | None:
    """The education registry suffix ``host`` sits under, or ``None``.

    Separate from :func:`official_suffix` on purpose; see :data:`ACADEMIC_SUFFIXES`.
    """
    return _longest_suffix(host, ACADEMIC_SUFFIXES)


def self_published(domain: str) -> str | None:
    """The self-publishing platform ``domain`` is a tenant of, or ``None``.

    ``alice.substack.com`` -> ``substack.com``. Read from
    :data:`~app.research.suffixes.MULTI_TENANT` rather than from a list of its own,
    because that table already enumerates exactly this set — the hosts where the
    subdomain is the author — for the neighbouring purpose of counting two authors on
    one platform as two publishers. One table, two readings, no drift.

    What it establishes is narrow and factual: the platform did not write this and does
    not vouch for it, so nobody with a masthead is accountable for the text. That bears
    on :attr:`~app.domain.credibility.Axis.RELIABILITY` and on nothing else. It is not
    a finding about the writing, and the writing may be the best thing in the dossier.

    Returns ``None`` for the platform's own domain — ``substack.com`` with no tenant in
    front of it is Substack the company, not somebody's newsletter.
    """
    key = _key(domain)
    for suffix in MULTI_TENANT:
        if key.endswith(f".{suffix}"):
            return suffix
    return None


def owner(domain: str) -> str | None:
    """The corporate group ``domain`` belongs to, or ``None``.

    An opaque slug, only ever compared against another call's result — see
    :data:`OWNERS` on why the value itself is never published, and on why this is the
    one table in the module whose gaps are not the safe direction.
    """
    return OWNERS.get(_key(domain))


def _longest_suffix(host: str, table: frozenset[str]) -> str | None:
    """The longest entry of ``table`` that ``host`` equals or sits beneath.

    Walks the labels rather than scanning the table, so the cost is the depth of the
    hostname — four or five — instead of the size of the table.
    """
    key = _key(host)
    if not key:
        return None
    labels = key.split(".")
    for start in range(len(labels)):
        candidate = ".".join(labels[start:])
        if candidate in table:
            return candidate
    return None


def _key(host: str) -> str:
    """Lower-cased, trailing dot removed. The only normalisation any lookup does."""
    return host.rstrip(".").lower()
