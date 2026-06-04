;;; setup_template.lsp
;;; Road Design Automation — DWG template setup script.
;;;
;;; PURPOSE
;;;   Creates all required layers, sets drawing environment variables, and
;;;   prints a completion checklist.  Run ONCE on a blank DWG before saving
;;;   it as your Civil 3D project template (.dwt) or project drawing (.dwg).
;;;
;;; USAGE
;;;   AutoCAD command line :  (load "setup_template.lsp")
;;;   Or drag-and-drop this file onto the AutoCAD drawing window.
;;;   The command C:RoadSetupTemplate runs automatically on load.
;;;   Re-run any time by typing  ROADSETUP  at the command prompt.

(defun c:ROADSETUP () (c:RoadSetupTemplate))

(defun c:RoadSetupTemplate ( / *error* _ensure-ltype _make-layer)

  (defun *error* (msg)
    (if (not (member msg '("Function cancelled" "quit / exit abort")))
      (princ (strcat "\n[RoadSetup] Error: " msg))
    )
    (princ)
  )

  ;; Load a linetype from acad.lin if not already present in the drawing.
  (defun _ensure-ltype (lname / )
    (if (not (tblsearch "LTYPE" lname))
      (command "_.LINETYPE" "_Load" lname "acad.lin" "")
    )
  )

  ;; Create a layer (ACI colour + linetype).  Report EXISTS if already present.
  ;; colour: integer ACI index
  ;;   1=red  2=yellow  3=green  4=cyan  5=blue  7=white  30=orange  252=grey
  (defun _make-layer (name colour ltype / )
    (if (tblsearch "LAYER" name)
      (princ (strcat "\n  [EXISTS]  " name))
      (progn
        (entmake
          (list
            '(0   . "LAYER")
            '(100 . "AcDbSymbolTableRecord")
            '(100 . "AcDbLayerTableRecord")
            (cons 2   name)
            '(70  . 0)
            (cons 62  colour)
            (cons 6   ltype)
          )
        )
        (princ (strcat "\n  [CREATED] " name))
      )
    )
  )

  ;; ═══════════════════════════════════════════════════════════════════════
  (princ "\n")
  (princ "\n  ╔══════════════════════════════════════════════╗")
  (princ "\n  ║   Road Design Automation — Template Setup   ║")
  (princ "\n  ╚══════════════════════════════════════════════╝")

  ;; ── 1. Linetypes ────────────────────────────────────────────────────────
  (princ "\n\n[1/4] Loading linetypes...")
  (_ensure-ltype "CONTINUOUS")
  (princ " done.")

  ;; ── 2. Layers ───────────────────────────────────────────────────────────
  (princ "\n\n[2/4] Creating layers:")

  ;; Alignment
  (_make-layer "C-ALIGN"         1   "CONTINUOUS")  ; red    — horizontal alignment CL
  (_make-layer "C-ALIGN-LABEL"   7   "CONTINUOUS")  ; white  — alignment labels / stationing
  (_make-layer "C-ALIGN-MISC"    1   "CONTINUOUS")  ; red    — PI markers, bearing lines

  ;; Profile
  (_make-layer "C-PROF-FG"       3   "CONTINUOUS")  ; green  — finished-grade profile
  (_make-layer "C-PROF-EG"       252 "CONTINUOUS")  ; grey   — existing-ground profile
  (_make-layer "C-PROF-LABEL"    7   "CONTINUOUS")  ; white  — profile labels, grade notes

  ;; Corridor & surfaces
  (_make-layer "C-CORR"          5   "CONTINUOUS")  ; blue   — corridor edge-of-pavement
  (_make-layer "C-SURF-EG"       252 "CONTINUOUS")  ; grey   — EG TIN surface triangles
  (_make-layer "C-SURF-FG"       3   "CONTINUOUS")  ; green  — FG TIN surface triangles

  ;; Markings & signage (targets for M5 / M7)
  (_make-layer "C-ROAD-MARK"     30  "CONTINUOUS")  ; orange — road marking solids (M7)
  (_make-layer "C-SGN-FURN"      4   "CONTINUOUS")  ; cyan   — sign block inserts (M5/M7)

  ;; General
  (_make-layer "C-ANNOT"         7   "CONTINUOUS")  ; white  — dimensions, text
  (_make-layer "C-XREF"          252 "CONTINUOUS")  ; grey   — xref / survey data (read-only)
  (_make-layer "C-BOUNDARY"      2   "CONTINUOUS")  ; yellow — project boundary / ROW

  ;; ── 3. Drawing environment ──────────────────────────────────────────────
  (princ "\n\n[3/4] Configuring drawing environment:")

  (setvar "LTSCALE"    1.0)  ; linetype scale = 1 (Civil 3D handles annotation scale)
  (setvar "MSLTSCALE"  1)    ; use model-space annotation scale for linetypes
  (setvar "INSUNITS"   6)    ; insertion units = metres
  (setvar "ANGBASE"    0)    ; 0° = East
  (setvar "ANGDIR"     0)    ; counter-clockwise = positive
  (setvar "AUNITS"     0)    ; angular units = decimal degrees
  (setvar "LUPREC"     3)    ; linear display precision — 3 decimal places
  (setvar "AUPREC"     4)    ; angular display precision — 4 decimal places
  (setvar "OSMODE"     4135) ; snap: endpoint + midpoint + intersection + perpendicular

  (princ "\n  LTSCALE=1      INSUNITS=6 (metres)")
  (princ "\n  ANGBASE=0      ANGDIR=0 (CCW from East)")
  (princ "\n  LUPREC=3       AUPREC=4")
  (princ "\n  OSMODE=4135    (endpoint / midpoint / intersection / perpendicular)")

  ;; ── 4. Completion checklist ─────────────────────────────────────────────
  (princ "\n\n[4/4] Layer & environment setup complete.")
  (princ "\n")
  (princ "\n  ┌─── Manual steps still required ─────────────────────────────────┐")
  (princ "\n  │                                                                  │")
  (princ "\n  │  1. Create alignment + profile STYLES named 'Standard'           │")
  (princ "\n  │     (or update styles.* keys in config/project.json).            │")
  (princ "\n  │                                                                  │")
  (princ "\n  │  2. Create the assembly 'BasicLaneAssembly' in the Toolspace     │")
  (princ "\n  │     (or match your names.assembly in project.json).              │")
  (princ "\n  │                                                                  │")
  (princ "\n  │  3. INSERT or WBLOCK-import block definitions for every sign     │")
  (princ "\n  │     listed in signage_schedule.csv (block_name column).          │")
  (princ "\n  │                                                                  │")
  (princ "\n  │  4. Import / create the EG (existing-ground) TIN surface and     │")
  (princ "\n  │     name it to match names.surface_eg in project.json.           │")
  (princ "\n  │                                                                  │")
  (princ "\n  │  5. Save this drawing as a .dwt template, or directly as your    │")
  (princ "\n  │     project .dwg before running Dynamo M1–M8.                    │")
  (princ "\n  │                                                                  │")
  (princ "\n  └──────────────────────────────────────────────────────────────────┘")
  (princ "\n")
  (princ)
)

;;; Auto-run when the file is loaded.
(c:RoadSetupTemplate)
