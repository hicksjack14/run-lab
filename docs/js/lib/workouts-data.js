// Content of the Workouts page: the daily circuit.

export const CIRCUIT = {
  minutes: 20,
  exercises: [
    { name: "Pull-ups", reps: 10, cue: "Full hang, chin over the bar, lower slowly.", scale: "Use a resistance band, or do slow lowering reps (jump up, lower for 3 to 5 seconds). Split into smaller sets if needed." },
    { name: "Push-ups", reps: 20, cue: "Hands under shoulders, body in one straight line, press both hands evenly.", scale: "Hands on a bench or counter to make it easier." },
    { name: "Crunches", reps: 25, cue: "Low back stays on the floor, lift your shoulder blades, breathe out on the way up.", scale: "Hands across the chest, not behind the head." },
    { name: "Squats", reps: 50, cue: "Feet shoulder-width, sit your hips back, knees over the middle toes (not caving in), heels down.", scale: "Squat to a chair or box. If knees or ankles ache, drop to 25." },
  ],
  note: "Run the clock for 20 minutes and repeat the round. Rest when you need to; rounds don't have to be fast. If knee or ankle ache keeps climbing, shorten the squats or take a day off.",
};

export const circuitRepsPerRound = () => CIRCUIT.exercises.reduce((t, e) => t + e.reps, 0);

// ------------------------------------------------------------------ guided calisthenics routines (pull-up bar + floor, 15-20 min)
// Step kinds: "reps" (do the reps, tap Done; `est` = rough seconds, only for the time estimate), "timed" (clock runs, auto-advances), "rest" (clock runs, auto-advances).
const MOVES = {
  pull: { name: "Pull-ups", cue: "Start from a full hang with shoulders pulled down away from your ears. Drive your elbows toward your ribs until your chin clears the bar, then lower for about 2 seconds to a full hang.", easier: "Use a band, or jump up and lower for 4 seconds. Split into sets of 3 or 4 with 10 seconds between." },
  push: { name: "Push-ups", cue: "Hands just outside your shoulders, body one straight line from head to heels. Chest to about a fist off the floor, then press the floor away.", easier: "Hands on a bench or counter, or knees down. Keep the straight line." },
  raise: { name: "Hanging leg raises", cue: "Hang from the bar and squeeze it hard. Lift straight legs until your toes are about bar height, no swinging, and lower for 2 seconds.", easier: "Bend your knees and bring them to your chest. If your grip gives out, do them lying on the floor." },
  squat: { name: "Squats", cue: "Feet shoulder-width, sit your hips back and down, knees track over your middle toes (don't cave in), heels stay down. Stand up fast, lower under control.", easier: "Squat to a chair. If knees or ankles ache, cut the reps in half." },
  lunge: { name: "Reverse lunges", cue: "Step one foot back and lower until the back knee hovers an inch off the floor, front shin close to vertical. Push through the front heel to stand. Alternate legs; the count is total reps.", easier: "Hold a doorframe, or go shallower." },
  crunch: { name: "Crunches", cue: "Low back stays on the floor. Lift your shoulder blades, breathe out on the way up, lower slowly.", easier: "Arms across your chest, never behind your head." },
  calf: { name: "Single-leg calf raises", cue: "Stand on one foot (fingertips on a wall for balance) and rise slowly onto your toes, hold one second, lower for 3 seconds. Count is total across both legs.", easier: "Two feet instead of one." },
  tib: { name: "Wall shin raises", cue: "Back against a wall, feet about a foot out. Keep your heels down and lift your toes toward your shins, slowly. Good for the front of the shin.", easier: "Move your feet closer to the wall." },
  bridge: { name: "Glute bridges", cue: "Lie on your back, knees bent, feet flat. Push through your heels to lift your hips until your body is one line from shoulders to knees, squeeze, lower.", easier: "Shorter range, or hold at the top for 1 second less." },
  hang: { name: "Dead hang", cue: "Hang from the bar with straight arms, shoulders slightly pulled down, breathe. Rest your feet on the floor or a chair if you need to take weight off.", easier: "Keep one foot on a chair." },
};
const reps = (k, n, est, extra = {}) => ({ kind: "reps", ...MOVES[k], reps: n, est, ...extra });
const timed = (k, secs, target, extra = {}) => ({ kind: "timed", ...MOVES[k], secs, target, ...extra });
const rest = (secs, name = "Rest") => ({ kind: "rest", name, secs, cue: "Shake your arms out, breathe slowly, sip water.", easier: "" });
const repeat = (n, build) => Array.from({ length: n }, (_, r) => build(r)).flat();

export const ROUTINES = [
  {
    id: "fedoseev", name: "Fedoseev 3×", minutes: 17,
    blurb: "From the bodyweight reel you saved on Yapper: 12 pull-ups, 10 leg raises, 25 push-ups, three times, then 100 squats. Heavy on the bar.",
    note: "The reel rests 4 minutes between rounds; this uses 3 so it fits in about 17 minutes. Stretch the rest back to 4 if your pull-ups fall apart, or cut them to 8 and add a round.",
    steps: [...repeat(3, (r) => [reps("pull", 12, 50), reps("raise", 10, 40), reps("push", 25, 60), ...(r < 2 ? [rest(180, `Rest after round ${r + 1}`)] : [])]), reps("squat", 100, 210, { name: "Finisher: 100 squats" })],
  },
  {
    id: "athletic", name: "Athletic circuit", minutes: 18,
    blurb: "Six moves, four rounds, minute-ish rests: pull-ups, push-ups, squats, leg raises, lunges, crunches. A lean, athletic, all-around circuit in the spirit of the Tom Holland-type routines.",
    note: "I don't have his exact routine, so this is the same idea built from your moves: full body, no gym, keep moving. Go at a speed where the last round is still clean.",
    steps: repeat(4, (r) => [reps("pull", 8, 35), reps("push", 15, 35), reps("squat", 20, 35), reps("raise", 10, 40), reps("lunge", 20, 40), reps("crunch", 20, 35), ...(r < 3 ? [rest(60, `Rest after round ${r + 1}`)] : [])]),
  },
  {
    id: "emom", name: "EMOM 18", minutes: 18,
    blurb: "Every minute on the minute: the clock starts a new move each minute. Finish the reps, rest what's left of the minute. 6 moves, 3 rounds.",
    note: "Pick reps you can finish in about 40 seconds. If you can't, drop the reps by 2 next round instead of stopping. If it's easy, add reps.",
    steps: repeat(3, () => [timed("pull", 60, "6 pull-ups"), timed("push", 60, "15 push-ups"), timed("squat", 60, "25 squats"), timed("raise", 60, "8 leg raises"), timed("lunge", 60, "16 lunges (8 each leg)"), timed("crunch", 60, "20 crunches")]),
  },
  {
    id: "runner", name: "Runner legs + bar", minutes: 16,
    blurb: "A leg-and-core circuit for running days, with shin and calf work built in, finished with a hang from the bar.",
    note: "Your Yapper saves on runner leg day and shin splints had no exercise list, so these are standard moves. Stop and skip anything that makes shin pain sharper.",
    steps: [...repeat(4, (r) => [reps("squat", 20, 35), reps("lunge", 16, 40), reps("calf", 30, 50), reps("tib", 20, 30), reps("bridge", 20, 40), ...(r < 3 ? [rest(45, `Rest after round ${r + 1}`)] : [])]), timed("hang", 45, "Hang as long as you can, up to 45 seconds", { name: "Finisher: dead hang" })],
  },
];

export const stepSecs = (st) => (st.kind === "reps" ? st.est : st.secs);
export const routineSecs = (r) => r.steps.reduce((t, s) => t + stepSecs(s), 0);
