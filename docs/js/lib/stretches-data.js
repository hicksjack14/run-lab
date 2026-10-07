// The content of the Stretches page: a timed 15-minute routine and the 20-minute daily circuit.
// `sides` is [label, seconds] pairs: the tighter (right) side comes first and gets the longer hold. `secs` is for a move done once.
// Wording is deliberately general (no diagnoses): this page is published on the public snapshot.

export const SAFETY = [
  "General guidance, not medical advice. Stretch to a mild pull (about 4 out of 10), never sharp or pinching pain. Hold steady and breathe; no bouncing.",
  "Stop and get it checked if pain is sharp, still there the next day, or comes with swelling, locking or the knee giving way. A physical therapist who knows your history can tailor this list: bring it with you.",
];

export const ROUTINE = [
  { id: "hops", name: "Lymphatic hops", area: "Warm-up", secs: 60,
    cues: ["Stand tall, feet hip-width apart, knees soft.", "Let your heels lift an inch and drop in a quick, springy bounce. Arms and shoulders loose.", "Keep it small and relaxed: shaking out, not jumping."],
    why: "Gets blood and fluid moving before you stretch, so the first holds go deeper and feel better.",
    easier: "Keep both feet on the floor and bounce through the knees only. Use a rug or mat if the ball of your foot is sore." },
  { id: "swings", name: "Body swings", area: "Warm-up", secs: 60,
    cues: ["Feet a little wider than your hips.", "Turn your torso left and right and let your arms swing and wrap loosely around you.", "Let the heel of the trailing foot lift as you turn. Turn through the hips, not just the back."],
    why: "Loosens the spine, hips and shoulders with easy rotation.",
    easier: "Smaller swings, or rest one hand on a wall. Let a stiffer arm just be carried along." },
  { id: "catcow", name: "Cat–cow", area: "Lower back", secs: 60,
    cues: ["Hands under shoulders, knees under hips, on a thick pad or folded towel.", "Breathe in: belly drops, chest lifts. Breathe out: round your back up toward the ceiling.", "Slow, about four seconds each way."],
    why: "Mobilizes the lower back and hips after a run.",
    easier: "Seated in a chair with hands on knees: same arch and round. Good if kneeling bothers the knee." },
  { id: "kneechest", name: "Knee to chest", area: "Lower back and hip", sides: [["Right", 30], ["Left", 30]],
    cues: ["Lie on your back. Hug one knee toward your chest; the other leg stays long or bent with the foot flat.", "Keep your lower back resting on the floor.", "Stop before the knee feels pinched."],
    why: "Eases the lower back and the back of the hip.",
    easier: "Hold behind the thigh instead of the shin if bending the knee all the way is uncomfortable." },
  { id: "figure4", name: "Figure-4 glute stretch", area: "Hip", sides: [["Right", 45], ["Left", 30]],
    cues: ["On your back, cross one ankle over the opposite knee to make a 4.", "Pull the bottom thigh toward you until you feel it in the glute of the crossed leg.", "Let the top knee relax; don't push it down hard."],
    why: "Tight glutes and hip rotators feed straight into knee and lower-back strain.",
    easier: "Seated version: sit in a chair, cross ankle over knee, lean forward with a flat back." },
  { id: "hamstring", name: "Hamstring stretch with a strap", area: "Leg", sides: [["Right", 45], ["Left", 30]],
    cues: ["On your back, loop a strap or towel around one foot and raise the leg.", "Other knee bent, foot flat. Back of the raised knee can stay softly bent.", "Feel the pull behind the thigh, not behind the knee."],
    why: "Tight hamstrings shorten your stride and tug on the knee.",
    easier: "Bend the raised knee a little, or lower the leg until the pull is mild." },
  { id: "deadbug", name: "Dead bug", area: "Core", secs: 60,
    cues: ["On your back, arms up toward the ceiling, knees bent over your hips.", "Slowly lower the opposite arm and leg toward the floor, then return. Alternate sides.", "Low back stays flat on the floor. Breathe out as you lower."],
    why: "Steady core control for your hips and back while you run.",
    easier: "Only lower the legs (tap a heel to the floor), arms stay up." },
  { id: "hipflexor", name: "Hip flexor stretch", area: "Hip", sides: [["Right", 45], ["Left", 30]],
    cues: ["Half-kneel on a thick folded towel, or stand in a long lunge stance (back heel up, no kneeling).", "Tuck your tailbone under and ease your hips forward until the front of the back hip stretches.", "Front knee stays over the middle toe. Don't let it fall inward."],
    why: "Running tightens the front of the hip, which tilts the pelvis and loads the lower back and knee.",
    easier: "Use the standing lunge instead of kneeling." },
  { id: "itband", name: "Standing side-bend (outer hip)", area: "Hip and outer thigh", sides: [["Right", 35], ["Left", 30]],
    cues: ["Stand next to a wall for balance. Cross the stretching leg behind the other.", "Reach the arm on that side overhead and lean away, pushing the hip out to the side.", "Feel it along the outer hip and thigh."],
    why: "The outer hip and thigh can pull on the knee. This eases it.",
    easier: "Lean your hand on the wall and keep the lean small." },
  { id: "calf", name: "Calf stretch, straight knee", area: "Ankle and calf", sides: [["Right", 60], ["Left", 30]],
    cues: ["Hands on a wall. Back foot flat with the heel down, back knee straight, toes pointing straight ahead.", "Lean in until you feel the upper calf. Keep the heel on the floor.", "Don't let the back foot roll outward."],
    why: "A tight calf limits ankle bend and pushes load onto the ball of the foot and the knee. The tighter side gets a longer hold.",
    easier: "Step the back foot in closer for a gentler pull, or hold a sturdy surface." },
  { id: "soleus", name: "Calf stretch, bent knee", area: "Ankle and calf", sides: [["Right", 45], ["Left", 30]],
    cues: ["Same wall position, but soften the back knee and sink down toward the heel.", "Heel stays down. Knee points over the middle toe, not caving inward.", "You should feel it lower in the calf, close to the ankle."],
    why: "Reaches the deeper calf muscle that straight-knee stretches miss. It helps the ankle bend for running.",
    easier: "Smaller knee bend." },
  { id: "toes", name: "Toe and ball-of-foot stretch", area: "Foot", sides: [["Right", 45], ["Left", 30]],
    cues: ["Sit with the ankle crossed over the opposite knee. Use your hand (or a towel) to bend the toes and the ball of the foot back toward the shin.", "Feel it in the arch and under the toes. Then pull just the big toe back for a few breaths.", "Gentle: no sharp pain under the ball of the foot."],
    why: "Opens the tight tissue under the toes where the ball of the foot gets sore.",
    easier: "Standing version: toes up against a wall, heel on the floor, lean in lightly." },
  { id: "ankle", name: "Ankle circles and alphabet", area: "Ankle", sides: [["Right", 40], ["Left", 30]],
    cues: ["Seated, lift one foot. Draw big, slow circles with the ankle, half the time each direction.", "Move only the ankle. Make the circles as large as you can.", "If you have time, trace the alphabet with your big toe."],
    why: "Keeps the ankle joint moving freely and helps circulation after a run.",
    easier: "Rest the heel on your other knee or on a pillow." },
];

export const EXTRAS = [
  { name: "Roll the ball of the foot", detail: "Roll a tennis ball slowly under the forefoot for 1 to 2 minutes. Skip it if the pain is sharp." },
  { name: "Clamshells", detail: "2 sets of 12 per side. Strengthens the outer hip so the knee tracks straighter." },
  { name: "Glute bridges", detail: "2 sets of 12. Squeeze the glutes at the top, ribs down, knees in line with the toes." },
  { name: "Hand, wrist and finger stretch", detail: "Arm straight, palm up, pull the fingers gently back with the other hand for 20 to 30 seconds. Then open and close the fist 10 times." },
  { name: "Quad stretch (left out of the timed routine)", detail: "Deep knee bending can be unfriendly to a knee with past injury. If you want it, lie on your stomach with a strap and stop at a mild pull." },
];

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

export const routineSeconds = () => ROUTINE.reduce((t, s) => t + (s.sides ? s.sides.reduce((a, [, n]) => a + n, 0) : s.secs), 0);
export const circuitRepsPerRound = () => CIRCUIT.exercises.reduce((t, e) => t + e.reps, 0);
