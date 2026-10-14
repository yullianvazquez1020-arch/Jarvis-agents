// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {JarvisTestToken} from "../src/JarvisTestToken.sol";

contract JarvisTestTokenTest is Test {
    JarvisTestToken t;
    address alice = address(0xA11CE);
    address bob = address(0xB0B);

    function setUp() public { t = new JarvisTestToken(); }

    function testMintSoloOwner() public {
        t.mint(alice, 10 ether);
        assertEq(t.balanceOf(alice), 10 ether);
        vm.prank(alice);
        vm.expectRevert(JarvisTestToken.NotOwner.selector);
        t.mint(alice, 1);
    }

    function testTransferYAllowance() public {
        t.mint(alice, 5 ether);
        vm.prank(alice); t.approve(bob, 2 ether);
        vm.prank(bob); t.transferFrom(alice, bob, 2 ether);
        assertEq(t.balanceOf(bob), 2 ether);
        assertEq(t.allowance(alice, bob), 0);
    }

    function testTope() public {
        uint256 cap = t.MAX_SUPPLY();
        vm.expectRevert(JarvisTestToken.CapExceeded.selector);
        t.mint(alice, cap + 1);
    }

    function testMainnetBloqueada() public {
        vm.chainId(1);
        vm.expectRevert(abi.encodeWithSelector(JarvisTestToken.MainnetBlocked.selector, 1));
        new JarvisTestToken();
    }
}
