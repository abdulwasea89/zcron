# Acron workspace interface

Updated: 2026-10-10

## Direction and references

A quiet, document-like workspace inspired by Notion: a clear page title,
compact controls, neutral surfaces, and lists separated by subtle rules.
Spacing and typography establish hierarchy before borders or color.

References: [Notion sidebar](https://www.notion.com/help/navigate-with-the-sidebar),
[page styling](https://www.notion.com/help/customize-and-style-your-content), and
[buttons](https://www.notion.com/help/buttons). The sidebar documentation informs
expandable groups and separating AI chat history from general navigation.
These references describe product behavior; the dimensions below are Acron's
implementation choices, not measurements of Notion's internal design system.

## Typography and spacing

| Element | Size / line height | Weight |
| --- | --- | --- |
| Page title | 32 / 40px desktop, 26 / 33px small screens | 600 |
| Section title | 16 / 24px | 600 |
| Metric value | 28 / 32px, tabular numerals | 600 |
| Buttons, navigation, body | 14 / 20px | 400–500 |
| Secondary labels, dates | 12 / 16–18px | 400–500 |

Inter for interface text. Monospace belongs to code, not ordinary form labels.
Use sentence case. Spacing follows 4, 8, 12, 16, 24, 32, and 40px increments.
The desktop sidebar is 240px, shrinking to a 52px icon rail. Page gutters are
20px on narrow screens and 40px on desktop. Content is capped at 1240px.

## Controls and surfaces

- Desktop buttons: 32px minimum height, 14px text, 16px icons, 6px icon gap,
  10px horizontal padding, 4px corners. Coarse-pointer action buttons: 44px.
- Use one filled primary action per action group. Secondary actions have thin
  borders; navigation and incidental links use subtle hover backgrounds.
- Metrics have no individual card containers. Use a shared horizontal divider
  and thin vertical separators; switch to two columns on narrow screens.
- Use 6px corners and a soft neutral fill for the setup callout. The checklist
  expands on demand. Completed items have a checkmark as well as color.
- Recent payments are rows, with a readable amount and explicit status.
  Subscription details are property/value pairs, not a large promotional card.
- Reserve shadows for floating overlays. Remove texture from the workspace.

## Color and themes

The existing Notion light theme uses a white canvas, #f7f7f5 sidebar, #37352f
text, #73716d secondary text, and #1b70c4 primary actions. The blue is deliberately
darker than the prior theme to improve white-label contrast. Other theme choices
remain available; components read semantic variables rather than hardcoded colors.

## Navigation and behavior

Dashboard, Assistant, and Analytics retain visible labels when expanded.
Operations, Money, and Organization groups can collapse. Recent AI chats appear
in the Assistant context. There is one New chat control. Settings actions open
the existing settings dialog rather than an absent route.

Keep all tenant-scoped data requests unchanged. Do not insert fictional chart
series, growth percentages, or testimonials. A failed data request must not be
presented as zero usage, completed setup, or an empty review queue.

## Accessibility and verification

Controls have visible keyboard focus. Expandable groups expose aria-expanded
and aria-controls; native details provides the setup disclosure interaction.
Progress indicators have accessible values. Respect reduced-motion preferences.
Verify desktop and narrow layouts, light and dark themes, settings entry points,
sidebar groups, and keyboard expansion before accepting a design iteration.
