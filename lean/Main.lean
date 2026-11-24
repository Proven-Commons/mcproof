import Mcproof

open Mcproof
open Mcproof.TransitionBounds
open Mcproof.AdapterBounds

private def parseInt? (s : String) : Option Int :=
  s.toInt?

private def parseNat? (s : String) : Option Nat :=
  s.toNat?

private def parseNatList? : List String → Option (List Nat)
  | [] => some []
  | x :: xs =>
    match parseNat? x, parseNatList? xs with
    | some v, some rest => some (v :: rest)
    | _, _ => none

private def parsePairs? : List String → Option (List (Nat × Nat))
  | [] => some []
  | [_] => none
  | wStr :: dStr :: rest =>
    match parseNat? wStr, parseNat? dStr, parsePairs? rest with
    | some w, some d, some tail => some ((w, d) :: tail)
    | _, _, _ => none

def main (args : List String) : IO UInt32 := do
  match args with
  | ["clamp", loStr, hiStr, xStr] =>
    match parseNat? loStr, parseNat? hiStr, parseNat? xStr with
    | some lo, some hi, some x =>
      IO.println s!"{clampNat lo hi x}"
      return 0
    | _, _, _ =>
      IO.eprintln "invalid natural numbers"
      return 2
  | ["bezout", aStr, bStr, xStr, yStr, gStr] =>
    match parseInt? aStr, parseInt? bStr, parseInt? xStr, parseInt? yStr, parseInt? gStr with
    | some a, some b, some x, some y, some g =>
      IO.println (if bezoutCheck a b x y g then "true" else "false")
      return 0
    | _, _, _, _, _ =>
      IO.eprintln "invalid integers"
      return 2
  | ["ratle", n1Str, d1Str, n2Str, d2Str] =>
    match parseInt? n1Str, parseInt? d1Str, parseInt? n2Str, parseInt? d2Str with
    | some n1, some d1, some n2, some d2 =>
      IO.println (if ratLeCross n1 d1 n2 d2 then "true" else "false")
      return 0
    | _, _, _, _ =>
      IO.eprintln "invalid integers"
      return 2
  | "segments" :: segs =>
    match cleanSegments segs with
    | some ok =>
      IO.println ("OK:" ++ String.intercalate "/" ok)
      return 0
    | none =>
      IO.println "REJECT"
      return 0
  | ["prefund", hStr, cStr, rStr] =>
    match parseNat? hStr, parseNat? cStr, parseNat? rStr with
    | some hVal, some cVal, some rVal =>
      IO.println s!"{prefundedVal hVal cVal rVal}"
      return 0
    | _, _, _ =>
      IO.eprintln "invalid natural numbers"
      return 2
  | "dualfloor" :: scaleStr :: pairArgs =>
    match parseNat? scaleStr, parsePairs? pairArgs with
    | some scale, some pairs =>
      IO.println s!"{dualFloorNat scale pairs}"
      return 0
    | _, _ =>
      IO.eprintln "invalid dualfloor arguments"
      return 2
  | ["cyclicdist", kStr, aStr, bStr] =>
    match parseNat? kStr, parseNat? aStr, parseNat? bStr with
    | some k, some a, some b =>
      IO.println s!"{cyclicSwitchDist k a b}"
      return 0
    | _, _, _ =>
      IO.eprintln "invalid cyclicdist arguments"
      return 2
  | ["ceildiv", numStr, scaleStr] =>
    match parseNat? numStr, parseNat? scaleStr with
    | some num, some scale =>
      IO.println s!"{ceilDivNat num scale}"
      return 0
    | _, _ =>
      IO.eprintln "invalid ceildiv arguments"
      return 2
  | ["tangentproj", h1Str, h2Str, d1Str, d2Str] =>
    match parseInt? h1Str, parseInt? h2Str, parseInt? d1Str, parseInt? d2Str with
    | some h1, some h2, some d1, some d2 =>
      let out := tangentProjScaled [h1, h2] [d1, d2]
      IO.println (String.intercalate "," (out.map toString))
      return 0
    | _, _, _, _ =>
      IO.eprintln "invalid tangentproj arguments"
      return 2
  | "sumsq" :: natArgs =>
    match parseNatList? natArgs with
    | some ds =>
      IO.println s!"{sumSqNat ds}"
      return 0
    | none =>
      IO.eprintln "invalid sumsq arguments"
      return 2
  | _ =>
    IO.eprintln "usage: mcproof_lean (clamp|bezout|ratle|segments|prefund|dualfloor|cyclicdist|ceildiv|tangentproj|sumsq) ..."
    return 2
