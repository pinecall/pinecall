// Fixture agent loaded through tsx by the serve entry: it names its callers in the class and holds a file of them too.

import { Agent, agent } from "../../../../../src/index.js";

/** Atiende el mostrador. */
@agent({ personas: ["in-a-hurry"] })
export default class FrontDesk extends Agent {}
