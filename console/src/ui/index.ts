/** The console's vocabulary, one import. */

import "./ui.css";
import "./tiles.css";

export { Card, CardAction, CardFoot, CardHead, Empty, Item, KV, Refused, Row, SectionLabel } from "./card";
export { Button, ButtonLink, Check, Chips, Field, Input, Label, Segmented, Switch, TextAction, TextArea } from "./controls";
export type { ButtonKind, ButtonSize } from "./controls";
export { Icon } from "./icon";
export { Select, SelectItem } from "./select";
export type { IconName } from "./icon";
export { Avatar, Bar, Dot, Pill, Tag, tintAt, tintOf } from "./marks";
export { initialsOf } from "@pinecall/core/initials";
export type { AvatarSize, Tint, Tone } from "./marks";
export { Page, PageHead } from "./page";
export { Stat, Stats } from "./stat";
export { TableHead, TableRow } from "./table";
export { usePane } from "./resize";
export type { Pane } from "./resize";
export { Tabs } from "./tabs";
export type { TabItem } from "./tabs";
