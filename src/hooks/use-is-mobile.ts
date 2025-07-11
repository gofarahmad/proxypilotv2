
"use client"

import * as React from "react"

// This hook is used to determine if the current viewport is mobile-sized.
// It defaults to a specific breakpoint but is a common pattern for creating
// responsive layouts in React without relying solely on CSS media queries.
const MOBILE_BREAKPOINT = 768

export function useIsMobile() {
  const [isMobile, setIsMobile] = React.useState<boolean | undefined>(undefined)

  React.useEffect(() => {
    // Client-side only check
    if (typeof window === "undefined") {
      return;
    }

    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
    
    const onChange = () => {
      setIsMobile(mql.matches)
    }

    mql.addEventListener("change", onChange)
    
    // Set the initial value
    setIsMobile(mql.matches)

    return () => mql.removeEventListener("change", onChange)
  }, [])

  return isMobile;
}
