// Colours that tell the compared accounts apart on the Comparison page
// (numbered inputs, card avatars, table swatches, chart series).
// Validated with the dataviz palette script against white (all checks pass;
// orange is below 3:1 contrast, which is why every chart also has a legend
// and a table view).
export const SERIES_COLORS = ['#833AB4', '#E1306C', '#F77737', '#405DE6']

// The four checks that feed the Trust Score, in a fixed order so every
// chart and table lists them the same way.
export const MODULE_LABEL = {
  fake_follower: 'Account authenticity',
  engagement: 'Engagement',
  misinformation: 'Misinformation',
  credential: 'Credentials',
}
export const MODULE_ORDER = ['fake_follower', 'engagement', 'misinformation', 'credential']
