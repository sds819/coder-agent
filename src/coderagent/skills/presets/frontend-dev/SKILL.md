---
name: frontend-dev
description: Build a web page or a component - HTML, CSS, JavaScript or React - with a layout that works on a phone and on a desktop.
---

# Frontend

## Steps

1. **Look at what is there.** Find the stack: the files of the page, the
   framework, the CSS it uses, the command that starts it. Build inside
   that stack; do not add a framework to a page that has none.
2. **Write the markup.** Semantic elements first: `header`, `nav`, `main`,
   `section`, `footer`. A `div` soup is a sign the structure was not
   thought about.
3. **Write the style.** One system: spacing steps, two or three text sizes,
   one accent colour. Colours, spacing and radii are variables at the top of
   the file, not values scattered in the rules.
4. **Make it work on a phone.** The layout works at 360 pixels wide before
   it looks good on a wide screen.
5. **Check it.** Run the project's build and its tests. When the page can be
   opened, open it and look at it: the console has to be quiet and the
   layout must not break.

## Rules

- No dependency without a reason the user can see.
- Images and fonts that are not local are a failure when the machine is
  offline: keep the page working without the network.
- Accessibility is part of the build: a label for every input, an
  `alt` for every image, a visible focus, and a contrast that can be read.
- Do not refactor the code around the change. The page is the deliverable.
