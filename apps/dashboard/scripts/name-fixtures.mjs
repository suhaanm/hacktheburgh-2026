// Gives the made-up firm's people made-up, realistic full names in the dashboard's example data. Run it after copying the samples:
//
//   node scripts/name-fixtures.mjs            adds `name` where a person row has none (never overwrites a name the engine sent)
//   node scripts/name-fixtures.mjs --force    replaces every `name`
//   node scripts/name-fixtures.mjs --check    changes nothing; exits 1 if a person row is missing its name or a name is reused
//
// MAPPING RULE (deterministic, so the same firm always gets the same names, and the engine's own names can replace these later):
//   1. Collect every person label ("BP-07", "DA-02", "PG-11") in src/fixtures/firm-firm.json, sorted in natural order.
//   2. For each label in that order, start at index FNV-1a-32(label) mod NAMES.length and step forward (wrapping) to the first name no
//      earlier label in this firm took. A name is therefore never reused inside one firm, as long as the firm has no more people than
//      there are names (the list has 100; the firm has 60).
//   3. The same label gets the same name in every fixture (the worker's "what my admin can see" preview in home-sharing.json uses it too).
// The label stays the stable key and the aria id; screens show `name ?? label`.
//
// The names are invented: first and last names from many backgrounds, paired by hand to avoid anyone well known. They name no real person.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const NAMES = [
  "Amara Okafor", "Tomasz Wrobel", "Priya Raghunathan", "Mateo Salazar", "Hana Kobayashi", "Dmitri Voronin", "Fatima Al-Sayed", "Kwame Mensah",
  "Ingrid Lindqvist", "Rohan Deshpande", "Leila Haddad", "Joaquin Echeverria", "Mei Tan", "Oluwaseun Adebayo", "Siobhan Gallagher", "Anders Nystrom",
  "Yara Karimi", "Kenji Matsuda", "Thandiwe Dlamini", "Marek Kowalczyk", "Noor Rahimi", "Cormac Brennan", "Esperanza Villanueva", "Ravi Menon",
  "Katarzyna Nowak", "Idris Bello", "Freya Holloway", "Santiago Cardoso", "Aiko Yamamoto", "Emeka Eze", "Ottilie Pemberton", "Tariq Rashid",
  "Lucia Ferrero", "Bao Nguyen", "Ayesha Qureshi", "Henrik Halvorsen", "Zainab Abubakar", "Rhys Llewellyn", "Imani Boateng", "Pavel Novak",
  "Sunita Iyer", "Declan Quinn", "Mariam Sesay", "Takeshi Morita", "Gwen Hartley", "Abdullahi Warsame", "Elodie Marchetti", "Vikram Subramanian",
  "Nadia Petrova", "Fergus Lowry", "Chiamaka Obi", "Luca Bianchi", "Soo-jin Han", "Bartosz Zielinski", "Anjali Kulkarni", "Kofi Asante",
  "Maren Bjornsen", "Hamza Chaudhry", "Isla Mackenzie", "Rafael Quintero", "Wanjiru Kamau", "Stellan Berg", "Parisa Tehrani", "Eoin Doyle",
  "Adaeze Nwosu", "Matthias Keller", "Lakshmi Pillai", "Dara Sheridan", "Yusuf Demir", "Greta Lindgren", "Arjun Bhatt", "Ximena Ortega",
  "Cian Maguire", "Halima Suleiman", "Jonas Eriksen", "Meera Joshi", "Osei Appiah", "Tamsin Ridley", "Nikolai Sokolov", "Farah Siddiqui",
  "Ewan Calder", "Beatriz Lacerda", "Sandeep Grewal", "Ilse Vandermeer", "Jamal Whitfield", "Orla Keane", "Kazuki Fujimoto", "Branwen Pryce",
  "Mustafa Aydin", "Daria Kovac", "Ansel Thorne", "Chidi Okonkwo", "Rania Khoury", "Tobias Lehmann", "Nkechi Umeh", "Lorcan Mulvey",
  "Selin Yildiz", "Anil Reddy", "Briony Castle", "Emre Kaya",
];

/** FNV-1a, 32 bit. */
export function fnv1a(s) {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return h >>> 0;
}
const natural = (a, b) => a.localeCompare(b, "en", { numeric: true });

/** label -> name for one firm. Natural order of labels, hash start, first unused name. */
export function assignNames(labels) {
  const sorted = [...new Set(labels)].sort(natural);
  if (sorted.length > NAMES.length) throw new Error(`${sorted.length} people but only ${NAMES.length} names`);
  const taken = new Set();
  const out = new Map();
  for (const label of sorted) {
    let i = fnv1a(label) % NAMES.length;
    while (taken.has(i)) i = (i + 1) % NAMES.length;
    taken.add(i);
    out.set(label, NAMES[i]);
  }
  return out;
}

const here = dirname(fileURLToPath(import.meta.url));
const fx = join(here, "..", "src", "fixtures");
// Two-space-free formatting like the engine's samples: one space indent, sorted keys.
const sortKeys = (v) => (Array.isArray(v) ? v.map(sortKeys) : v && typeof v === "object" ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, sortKeys(v[k])])) : v);
const read = (f) => JSON.parse(readFileSync(join(fx, f), "utf8"));
const write = (f, v) => writeFileSync(join(fx, f), JSON.stringify(sortKeys(v), null, 1) + "\n");

function main() {
  const args = process.argv.slice(2);
  const force = args.includes("--force");
  const check = args.includes("--check");
  const firm = read("firm-firm.json");
  const users = firm.data.roles.flatMap((r) => r.users);
  const names = assignNames(users.map((u) => u.label));
  let changed = 0;
  const problems = [];
  for (const u of users) {
    const want = names.get(u.label);
    if (!u.name || force) { if (u.name !== want) { u.name = want; changed++; } }
  }
  // The worker's own preview of what an admin sees carries the same name for the same label.
  const sharing = read("home-sharing.json");
  const prev = sharing.data.preview;
  if (prev && prev.label) {
    const want = names.get(prev.label) ?? NAMES[fnv1a(prev.label) % NAMES.length];
    if (!prev.name || force) { if (prev.name !== want) { prev.name = want; changed++; } }
  }
  const all = users.map((u) => u.name);
  if (all.some((n) => !n)) problems.push("a person row has no name");
  if (new Set(all).size !== all.length) problems.push("a name is reused inside the firm");
  if (prev?.label && users.some((u) => u.label === prev.label && u.name !== prev.name)) problems.push("the preview's name differs from the firm's name for the same label");
  if (check) {
    console.log(problems.length ? `FAIL: ${problems.join("; ")}` : `OK: ${users.length} people, all named, no name reused`);
    process.exit(problems.length ? 1 : 0);
  }
  write("firm-firm.json", firm);
  write("home-sharing.json", sharing);
  console.log(`${changed} names written for ${users.length} people${problems.length ? "; problems: " + problems.join("; ") : ""}`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main();
