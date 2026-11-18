"""The platform's first sentences in a call's language: written here, or written once by the box's model and kept."""

import asyncio
import json
import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.enums import Stage
from runtime.exceptions import PinecallError
from runtime.kit.crypto import Vault
from runtime.kit.text import a_mapping
from runtime.platform import service as platform
from runtime.providers import service as providers
from runtime.providers.catalog import Catalog
from runtime.providers.stage import Model, Running, primary_language

logger = logging.getLogger(__name__)

# Where the org's name goes in the sentence that says who is calling.
THE_ORG = "{org}"
FALLBACK_LANGUAGE = "en"
# The box's row a language's sentences are kept in once a model wrote them: `sentences/sw`.
KEPT_UNDER = "sentences/"
LONGEST_SENTENCE = 300
# One request, and not long: the call that asks is opening, and says them in English if it is not answered
# in time. The vendor is told ten seconds because Google refuses a deadline under ten ("Manually set
# deadline 6s is too short", a 400 that left a call in Swahili its English sentences, 2026-11-18); the
# call stops waiting sooner.
ASKED_WITHIN = providers.Patience(within_s=10.0, retries=0)
WAITED_S = 6.0
THE_WRITING = "write its first sentences in the call's language"

# An outbound call says who is calling, and a recorded one that it is, before anything else. Each
# sentence is phrased so the org's name stands as it is written, with no ending or article of the
# language attached to it.
CALLING_FOR = {
    "en": "This is an automated assistant calling on behalf of {org}.",
    "es": "Le habla un asistente automático en nombre de {org}.",
    "pt": "Este é um assistente automático que liga em nome de {org}.",
    "fr": "Je suis un assistant automatique et je vous appelle au nom de {org}.",
    "de": "Hier spricht ein automatischer Assistent im Auftrag von {org}.",
    "it": "Sono un assistente automatico che chiama per conto di {org}.",
    "nl": "U spreekt met een automatische assistent die belt namens {org}.",
    "ca": "Li parla un assistent automàtic en nom de {org}.",
    "sv": "Det här är en automatisk assistent som ringer på uppdrag av {org}.",
    "da": "Dette er en automatisk assistent, der ringer på vegne af {org}.",
    "nb": "Dette er en automatisk assistent som ringer på vegne av {org}.",
    "no": "Dette er en automatisk assistent som ringer på vegne av {org}.",
    "fi": "Tämä on automaattinen avustaja, joka soittaa organisaation {org} puolesta.",
    "pl": "Tu automatyczny asystent, dzwonię w imieniu {org}.",
    "cs": "Zde automatický asistent, volám jménem {org}.",
    "ro": "Sunt un asistent automat și vă sun din partea {org}.",
    "hu": "Automata asszisztens vagyok, és a következő nevében telefonálok: {org}.",
    "el": "Σας καλεί ένας αυτόματος βοηθός εκ μέρους του εξής οργανισμού: {org}.",
    "tr": "{org} adına arayan otomatik bir asistanım.",
    "ru": "Вам звонит автоматический помощник от имени {org}.",
    "uk": "Вам телефонує автоматичний помічник від імені {org}.",
    "ar": "هذا مساعد آلي يتصل بالنيابة عن {org}.",
    "he": "מדבר עוזר אוטומטי שמתקשר מטעם {org}.",
    "fa": "این یک دستیار خودکار است که از طرف {org} تماس می‌گیرد.",
    "hi": "यह {org} की ओर से कॉल करने वाला एक स्वचालित सहायक है।",
    "bn": "এটি {org}-এর পক্ষ থেকে কল করা একটি স্বয়ংক্রিয় সহকারী।",
    "ta": "இது {org} சார்பாக அழைக்கும் தானியங்கி உதவியாளர்.",
    "te": "ఇది {org} తరపున కాల్ చేస్తున్న ఆటోమేటెడ్ అసిస్టెంట్.",
    "mr": "हा {org} च्या वतीने कॉल करणारा स्वयंचलित सहाय्यक आहे.",
    "gu": "આ {org} વતી કૉલ કરનાર સ્વચાલિત સહાયક છે.",
    "kn": "ಇದು {org} ಪರವಾಗಿ ಕರೆ ಮಾಡುತ್ತಿರುವ ಸ್ವಯಂಚಾಲಿತ ಸಹಾಯಕ.",
    "ml": "ഇത് {org} എന്ന സ്ഥാപനത്തിന് വേണ്ടി വിളിക്കുന്ന ഒരു ഓട്ടോമേറ്റഡ് അസിസ്റ്റന്റ് ആണ്.",
    "pa": "ਇਹ {org} ਵੱਲੋਂ ਕਾਲ ਕਰ ਰਿਹਾ ਇੱਕ ਸਵੈਚਾਲਿਤ ਸਹਾਇਕ ਹੈ।",
    "id": "Ini adalah asisten otomatis yang menelepon atas nama {org}.",
    "vi": "Đây là trợ lý tự động gọi thay mặt cho {org}.",
    "th": "นี่คือผู้ช่วยอัตโนมัติที่โทรในนามของ {org}",
    "ja": "こちらは{org}に代わってお電話している自動アシスタントです。",
    "ko": "{org} 측을 대신하여 전화드리는 자동 안내 도우미입니다.",
    "zh": "这是代表{org}致电的自动助理。",
}
MAY_BE_RECORDED = {
    "en": "This call may be recorded.",
    "es": "Esta llamada puede ser grabada.",
    "pt": "Esta chamada pode ser gravada.",
    "fr": "Cet appel peut être enregistré.",
    "de": "Dieser Anruf kann aufgezeichnet werden.",
    "it": "Questa chiamata può essere registrata.",
    "nl": "Dit gesprek kan worden opgenomen.",
    "ca": "Aquesta trucada pot ser gravada.",
    "sv": "Det här samtalet kan komma att spelas in.",
    "da": "Denne samtale kan blive optaget.",
    "nb": "Denne samtalen kan bli tatt opp.",
    "no": "Denne samtalen kan bli tatt opp.",
    "fi": "Tämä puhelu voidaan nauhoittaa.",
    "pl": "Ta rozmowa może być nagrywana.",
    "cs": "Tento hovor může být nahráván.",
    "ro": "Acest apel poate fi înregistrat.",
    "hu": "A hívást rögzíthetjük.",
    "el": "Αυτή η κλήση ενδέχεται να ηχογραφηθεί.",
    "tr": "Bu görüşme kayıt altına alınabilir.",
    "ru": "Этот разговор может быть записан.",
    "uk": "Цю розмову може бути записано.",
    "ar": "قد يتم تسجيل هذه المكالمة.",
    "he": "ייתכן שהשיחה הזו תוקלט.",
    "fa": "این تماس ممکن است ضبط شود.",
    "hi": "यह कॉल रिकॉर्ड की जा सकती है।",
    "bn": "এই কলটি রেকর্ড করা হতে পারে।",
    "ta": "இந்த அழைப்பு பதிவு செய்யப்படலாம்.",
    "te": "ఈ కాల్ రికార్డ్ చేయబడవచ్చు.",
    "mr": "हा कॉल रेकॉर्ड केला जाऊ शकतो.",
    "gu": "આ કૉલ રેકોર્ડ થઈ શકે છે.",
    "kn": "ಈ ಕರೆಯನ್ನು ರೆಕಾರ್ಡ್ ಮಾಡಬಹುದು.",
    "ml": "ഈ കോൾ റെക്കോർഡ് ചെയ്യപ്പെട്ടേക്കാം.",
    "pa": "ਇਹ ਕਾਲ ਰਿਕਾਰਡ ਕੀਤੀ ਜਾ ਸਕਦੀ ਹੈ।",
    "id": "Panggilan ini mungkin direkam.",
    "vi": "Cuộc gọi này có thể được ghi âm.",
    "th": "การโทรนี้อาจมีการบันทึกเสียง",
    "ja": "この通話は録音される場合があります。",
    "ko": "이 통화는 녹음될 수 있습니다.",
    "zh": "本次通话可能会被录音。",
}

INSTRUCTIONS = (
    "You write the two fixed sentences an automated phone assistant says at the start of a call, in the "
    "language whose tag is `{language}`. Write them as a native speaker says them aloud on a formal call: "
    "natural, polite, one sentence each. `calling_for` keeps the text {{org}} exactly as written, once: an "
    "organisation's name takes its place, so phrase the sentence so that the name needs no ending, article "
    "or particle of the language attached to it. Answer with one JSON object and nothing else: "
    '{{"calling_for": "…", "may_be_recorded": "…"}}.'
)
THE_SENTENCES = (
    'calling_for: "This is an automated assistant calling on behalf of {org}."\n'
    'may_be_recorded: "This call may be recorded."'
)


@dataclass(frozen=True, slots=True)
class Sentences:
    """What a call says first where its org wrote nothing of its own: who is calling, and that it is recorded."""

    # Holds `{org}` where the org's name goes.
    calling_for: str
    may_be_recorded: str


# A legal sentence said in a language its caller does not speak tells them nothing: until 2026-11-18 a
# call in any language but the eight written here opened with the English ones.
async def sentences_in(session: AsyncSession, vault: Vault, language: str | None) -> Sentences:
    """The sentences in the call's main language: the written ones, the kept ones, or written now and kept."""
    spoken = primary_language(language) or FALLBACK_LANGUAGE
    found = await _find(session, spoken)
    if found is not None:
        return found
    written = await _write(session, vault, spoken)
    if written is None:
        return _say_written(FALLBACK_LANGUAGE)
    await platform.put_setting_if_absent(session, _declare_kept(spoken), written)
    return written


# What the judges of a finished call are told it opened with: nothing is written for them.
async def read_sentences(session: AsyncSession, language: str | None) -> Sentences:
    """The sentences a call in the language said: the written ones or the kept ones, English where neither."""
    found = await _find(session, primary_language(language) or FALLBACK_LANGUAGE)
    return _say_written(FALLBACK_LANGUAGE) if found is None else found


def read_written(answered: str) -> Sentences | None:
    """The two sentences a model answered, or None where it answered anything else."""
    opens, closes = answered.find("{"), answered.rfind("}")
    try:
        said: object = json.loads(answered[opens : closes + 1]) if opens >= 0 else None
    except ValueError:
        return None
    if not a_mapping(said):
        return None
    calling_for, may_be_recorded = said.get("calling_for"), said.get("may_be_recorded")
    if not isinstance(calling_for, str) or not isinstance(may_be_recorded, str):
        return None
    read = Sentences(" ".join(calling_for.split()), " ".join(may_be_recorded.split()))
    sound = read.calling_for.count(THE_ORG) == 1 and read.calling_for.count("{") == 1
    sound = sound and "{" not in read.may_be_recorded and read.may_be_recorded != ""
    return read if sound and max(len(read.calling_for), len(read.may_be_recorded)) <= LONGEST_SENTENCE else None


# ── private ──


async def _find(session: AsyncSession, spoken: str) -> Sentences | None:
    if spoken in CALLING_FOR:
        return _say_written(spoken)
    return await platform.find_setting(session, _declare_kept(spoken))


def _say_written(language: str) -> Sentences:
    return Sentences(CALLING_FOR[language], MAY_BE_RECORDED[language])


def _declare_kept(language: str) -> platform.Setting[Sentences]:
    return platform.Setting(f"{KEPT_UNDER}{language}", _load, asdict)


def _load(value: Mapping[str, Any]) -> Sentences:
    return Sentences(calling_for=str(value["calling_for"]), may_be_recorded=str(value["may_be_recorded"]))


# A model that does not answer, or answers what is not the two sentences, leaves the call its English
# ones and nothing kept: the next call in the language asks again.
async def _write(session: AsyncSession, vault: Vault, language: str) -> Sentences | None:
    catalog = await providers.get_catalog(session)
    try:
        running = await _find_the_boxs_model(session, vault, catalog)
        lines = [
            providers.Line("system", INSTRUCTIONS.format(language=language)),
            providers.Line("user", THE_SENTENCES),
        ]
        async with asyncio.timeout(WAITED_S), providers.open_answerer(running) as model:
            answered = (await model.ask(lines, what=THE_WRITING, patience=ASKED_WITHIN)).text
    except (PinecallError, TimeoutError) as refused:
        logger.warning("the first sentences in %s were not written: %s", language, refused or "no answer in time")
        return None
    written = read_written(answered)
    if written is None:
        logger.warning("the first sentences in %s were not written: the model answered %r", language, answered[:200])
    return written


# The judge's model where the row names one, else the one calls think with: on the box's own key, as
# the judges at a hang-up run.
async def _find_the_boxs_model(session: AsyncSession, vault: Vault, catalog: Catalog) -> Running:
    row = catalog.defaults[Stage.llm] if catalog.judge is None else catalog.judge.llm
    box = await providers.box_credentials(session, vault)
    named = Model(vendor=row.vendor, model=row.model or "")
    return providers.stage_on_its_key(Stage.llm, named, catalog, providers.Keyring(box=box))
