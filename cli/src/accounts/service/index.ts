/** Accounts: signing this machine in, the person's orgs, who a key is, the org's secrets and its people. */

export type { MemberRow, Org, SecretList, SecretRow, Whoami } from "../../api/accounts.js";
export { homeOf } from "../../kit/home.js";
export { readCallerNumber, readSignIn, writeCallerNumber, type MachineSignIn } from "../../project/session.js";
export type { Advice } from "../../api/providers.js";
export { adviceAt, chooseOrg, listOrgs, slugOf, whichOrg } from "./orgs.js";
export { checkSecretName, listSecrets, removeSecret, setSecret, SetSecretInput } from "./secrets.js";
export { listTeam, resetLink, setTeamPassword, SetPasswordInput, type ResetLink } from "./team.js";
export { machineSignIn, signInLink, startSignIn, StartSignInInput, TOOK_TOO_LONG, type SignedIn, type SignIn } from "./signin.js";
export { createLoginCode, getWhoami, orgOf, personOf } from "./whoami.js";
