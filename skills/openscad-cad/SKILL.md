---
name: openscad-cad
description: OpenSCAD mechanical CAD — parametric, low-poly parts exported to STL (game props, 3D prints).
domain: openscad
triggers: openscad, scad, cad, stl, 3d print, 3d printing, printable, gear, bracket, enclosure, mechanical, parametric, mount, hinge, knob, case
---
# OpenSCAD Mechanical CAD skill

OUTPUT FORMAT — one block, then one short sentence. Nothing else.
```openscad file=models/<name>.scad run
<code>
```
`run` compiles it: you get errors, the .stl, a .png preview and the triangle count.

RULES
- Millimeters. Every size is a variable at the top (parametric). `$fn = 32;` once at the top.
- Game assets: stay under 5000 triangles ($fn 24-48). Prints: $fn up to 96.
- Every statement ends with `;`. No `;` after a `}`.
- Variables never change: no `x = x + 1`. Loop: `for (i = [0:n-1]) ...` and compute from i.
- difference(): the FIRST child is the solid, every other child is cut away. Make cutters
  0.02 longer and start them at -0.01 so holes go all the way through.
- 2D shapes (circle, square, polygon, text) must be linear_extrude()d or rotate_extrude()d.

ONLY THESE EXIST
3D: cube([x,y,z], center=true) sphere(r=) cylinder(h=, r= | r1=,r2= | d=, center=true) polyhedron(points,faces)
2D: circle(r=) square([x,y], center=true) polygon(points=[[x,y],...]) text("A", size=10)
Ops: translate([x,y,z]) rotate([x,y,z]) scale([x,y,z]) mirror([1,0,0]) color("red")
     union() difference() intersection() hull() linear_extrude(height=, twist=, scale=) rotate_extrude()
Code: module name(a=1) { ... }  function f(x) = x*2;  let(a=1) ...  if (c) { } else { }  echo("x", x);
NOT BUILT IN (don't call): cone() box() torus() prism() fillet() chamfer() rounded_cube() print() return
  -> cone: cylinder(r1=, r2=0); rounded box: hull() of 8 spheres; torus: rotate_extrude() translate([R,0]) circle(r);

TEMPLATE — parametric gear
```openscad file=models/gear.scad run
$fn = 48;
teeth = 16;      // count
radius = 20;     // mm
tooth = 3;       // tooth size
thick = 5;
bore = 3;
difference() {
    linear_extrude(height = thick)
        union() {
            circle(r = radius);
            for (i = [0:teeth-1])
                rotate(i * 360 / teeth) translate([radius, 0]) square([tooth * 2, tooth], center = true);
        }
    translate([0, 0, -0.01]) cylinder(h = thick + 0.02, r = bore);
}
```

TEMPLATE — L bracket with two screw holes
```openscad file=models/bracket.scad run
$fn = 32;
width = 40; depth = 20; thick = 4; hole_r = 2.5;
difference() {
    union() {
        cube([width, depth, thick]);
        cube([thick, depth, width / 2]);
    }
    for (x = [12, width - 8])
        translate([x, depth / 2, -0.01]) cylinder(h = thick + 0.02, r = hole_r);
}
```
