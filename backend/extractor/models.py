from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CaseConfig:
    id: str
    detail_url: str
    expected_kind: str | None = None


@dataclass(frozen=True)
class FetchedDetail:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    content: bytes
    headers: dict[str, str]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_html(self) -> bool:
        return "text/html" in self.content_type.lower() or not self.content_type

    @property
    def text(self) -> str:
        for encoding in ("utf-8", "cp949", "euc-kr"):
            try:
                return self.content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return self.content.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class AttachmentRef:
    url: str
    filename: str
    source_text: str
    kind_hint: str = "attachment"


@dataclass(frozen=True)
class InlineImageRef:
    url: str
    alt: str
    source_text: str


@dataclass(frozen=True)
class DownloadedFile:
    url: str
    path: Path
    filename: str
    content_type: str
    size_bytes: int
    kind_hint: str = "attachment"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractedText:
    source: str
    method: str
    text: str
    status: str
    confidence: float | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AttachmentExtraction:
    url: str
    filename: str
    file_type: str
    status: str
    text: str
    methods: list[str]
    errors: list[str] = field(default_factory=list)
    content_type: str = ""
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceCandidate:
    source_id: str
    source_type: str
    origin_url: str
    filename: str = ""
    kind_hint: str = ""
    order_index: int = 0
    source_text: str = ""
    inline_ref: InlineImageRef | None = None
    attachment_ref: AttachmentRef | None = None
    direct_file: DownloadedFile | None = None


@dataclass
class StructuredSource:
    title: str = ""
    document_type: str = "other"
    summary_oneliner: str = ""
    requires_response: bool = False
    urgency: str = "normal"
    deadline: str = ""
    targets: list[str] = field(default_factory=list)
    key_facts: list[str] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)
    important_dates: list[str] = field(default_factory=list)
    preparation_items: list[str] = field(default_factory=list)
    fees: list[str] = field(default_factory=list)
    contacts: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    forms_to_submit: list[str] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    supplement_summary: list[str] = field(default_factory=list)
    activity_summary: list[str] = field(default_factory=list)
    unclassified: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CanonicalSummary:
    document_type: str = "other"
    summary_oneliner: str = ""
    requires_response: bool = False
    urgency: str = "normal"
    deadline: str = ""
    targets: list[str] = field(default_factory=list)
    key_facts: list[str] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)
    important_dates: list[str] = field(default_factory=list)
    preparation_items: list[str] = field(default_factory=list)
    fees: list[str] = field(default_factory=list)
    contacts: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    forms_to_submit: list[str] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    supplement_summary: list[str] = field(default_factory=list)
    activity_summary: list[str] = field(default_factory=list)
    unclassified: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceExtraction:
    source_id: str
    source_type: str
    source_role: str
    origin_url: str
    filename: str
    file_hash: str
    text_fingerprint: str
    duplicate_of: str | None
    extraction_method: str
    status: str
    raw_text: str
    structured: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    quality_score: float = 0.0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractionResult:
    case_id: str
    detail_url: str
    final_url: str
    content_kind: str
    status: str
    raw_text: str = ""
    sources: list[SourceExtraction] = field(default_factory=list)
    canonical_source_ids: list[str] = field(default_factory=list)
    canonical_summary: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    expected_kind: str | None = None

    # Deprecated compatibility fields kept while older local UI/reports migrate.
    html_text: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)
    image_texts: list[dict[str, Any]] = field(default_factory=list)
    attachment_texts: list[dict[str, Any]] = field(default_factory=list)
    combined_text: str = ""
    methods: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
