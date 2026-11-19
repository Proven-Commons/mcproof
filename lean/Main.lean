import Mcproof

open Mcproof

private def parseInt? (s : String) : Option Int :=
  s.toInt?

private def parseNat? (s : String) : Option Nat :=
  s.toNat?

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
  | _ =>
    IO.eprintln "usage: mcproof_lean (clamp|bezout|ratle|segments) ..."
    return 2
