export const addressFormFields = [
  {
    key: "address_line",
    label: "Street / building",
    type: "textarea" as const,
    optional: true,
    wide: true,
    section: "address" as const,
    placeholder: "Door no., street, area, landmark…",
  },
  {
    key: "district",
    label: "District",
    optional: true,
    section: "address" as const,
    placeholder: "e.g. Chennai",
  },
  {
    key: "state",
    label: "State",
    optional: true,
    section: "address" as const,
    placeholder: "e.g. Tamil Nadu",
  },
  {
    key: "pin_code",
    label: "PIN code",
    optional: true,
    section: "address" as const,
    placeholder: "6 digits",
  },
];
