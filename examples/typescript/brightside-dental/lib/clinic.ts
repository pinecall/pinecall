// The clinic's own systems, as the agents reach them: the agenda, the patients, the invoices.
// Your code, not Pinecall's: an agent's tools call whatever your business already runs on.

export interface Slot { day: string; time: string; with: string }
export interface Visit extends Slot { id: string; patient: string }
export interface Patient { id: string; name: string; phone: string }
export interface Invoice { id: string; patient: string; amount: number; paid: boolean }

// Dr. Patel keeps one time open every weekday morning.
const weekday = (day: string): boolean => [1, 2, 3, 4, 5].includes(new Date(`${day}T12:00:00Z`).getUTCDay());
const patients: Patient[] = [{ id: "p-1", name: "Ana Lopez", phone: "+14155550142" }];
const invoices: Invoice[] = [{ id: "inv-204", patient: "p-1", amount: 120, paid: true }];
const refunds: { invoice: string; reason: string }[] = [];

export const clinic = {
  free: (day: string): Slot[] => (weekday(day) ? [{ day, time: "09:30", with: "Dr. Patel" }] : []),
  book: (day: string, time: string, patient: string): Visit => ({ id: "v-1", day, time, with: "Dr. Patel", patient }),
  patientByPhone: (phone: string): Patient | undefined => patients.find((one) => one.phone === phone),
  invoicesOf: (patient: Patient): Invoice[] => invoices.filter((one) => one.patient === patient.id),
  askRefund: (invoice: string, reason: string): void => void refunds.push({ invoice, reason }),
};

/** When a visit starts, on the clinic's clock. */
export const startsAt = (visit: Visit): Date => new Date(`${visit.day}T${visit.time}:00-08:00`);
