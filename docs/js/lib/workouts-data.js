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
