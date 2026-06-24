package main

import (
	"fmt"
	runewidth "github.com/mattn/go-runewidth"
)

func mainScratchTest() {
	// Base character: ส (Sua - U+0E2a)
	// Combining vowel: ั (Mai Han Akat - U+0E31)
	// Combining tone: ้ (Mai Tho - U+0E49)
	fmt.Printf("Width of 'ส': %d\n", runewidth.RuneWidth('ส'))
	fmt.Printf("Width of 'ั' (U+0E31): %d\n", runewidth.RuneWidth(0x0E31))
	fmt.Printf("Width of '้' (U+0E49): %d\n", runewidth.RuneWidth(0x0E49))
	
	str := "สวัสดี" // Contains combining characters
	fmt.Printf("String '%s' has %d runes, runewidth.StringWidth = %d\n", str, len([]rune(str)), runewidth.StringWidth(str))
}
