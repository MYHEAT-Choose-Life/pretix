#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

import re
from decimal import Decimal
from typing import List, Tuple

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import CartPosition, Discount, Event, Organizer
from pretix.base.services.cross_selling import CrossSellingService


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
    )
    return event


def pattern(regex, **kwargs):
    return re.compile(regex), kwargs


cond_suffix = [
    pattern(r" in the same subevent$", subevent_mode=Discount.SUBEVENT_MODE_SAME),
    pattern(r" in distinct subevents$", subevent_mode=Discount.SUBEVENT_MODE_DISTINCT),
]
cond_patterns = [
    pattern(r"^Buy at least (?P<condition_min_count>\d+) of (?P<condition_limit_products>.+)$",
            condition_all_products=False),
    pattern(r"^Buy at least (?P<condition_min_count>\d+) products$",
            condition_all_products=True),
    pattern(r"^Spend at least (?P<condition_min_value>\d+)\$$",
            condition_all_products=True),
    pattern(r"^For every (?P<condition_min_count>\d+) of (?P<condition_limit_products>.+)$",
            condition_all_products=False),
    pattern(r"^For every (?P<condition_min_count>\d+) products$",
            condition_all_products=True),
]
benefit_patterns = [
    pattern(r"^get (?P<benefit_discount_matching_percent>\d+)% discount on them\.$",
            benefit_same_products=True),
    pattern(r"^get (?P<benefit_discount_matching_percent>\d+)% discount on everything\.$",
            benefit_same_products=True),
    pattern(r"^get (?P<benefit_discount_matching_percent>\d+)% discount on "
            r"(?P<benefit_only_apply_to_cheapest_n_matches>\d+) of them\.$",
            benefit_same_products=True),
    pattern(r"^get (?P<benefit_discount_matching_percent>\d+)% discount on "
            r"(?P<benefit_only_apply_to_cheapest_n_matches>\d+) of (?P<benefit_limit_products>.+)\.$",
            benefit_same_products=False),
    pattern(r"^get (?P<benefit_discount_matching_percent>\d+)% discount on "
            r"(?P<benefit_limit_products>.+)\.$",
            benefit_same_products=False),
]


def make_discount(description, event: Event):
    condition, benefit = description.split(', ')

    d = Discount(event=event, internal_name=description)
    d.save()

    def apply(patterns: List[Tuple[re.Pattern, dict]], input):
        for regex, options in patterns:
            m = regex.search(input)
            if m:
                fields = m.groupdict()
                for k, v in [*fields.items(), *options.items()]:
                    if '_limit_products' in k:
                        getattr(d, k).set([event.items.get(name=v)])
                    else:
                        setattr(d, k, v)
                input = input[:m.start(0)] + input[m.endpos:]
        if input != '':
            raise Exception("Unable to parse '{}'".format(input))

    apply(cond_suffix + cond_patterns, condition)
    apply(benefit_patterns, benefit)

    d.full_clean()
    d.save()
    return d


def validate_discount_rule(
        d,
        subevent_mode=Discount.SUBEVENT_MODE_MIXED,
        condition_all_products=True,
        condition_limit_products=[],
        condition_apply_to_addons=True,
        condition_ignore_voucher_discounted=False,
        condition_min_count=0,
        condition_min_value=Decimal('0.00'),
        benefit_same_products=True,
        benefit_limit_products=[],
        benefit_discount_matching_percent=Decimal('0.00'),
        benefit_only_apply_to_cheapest_n_matches=None,
        benefit_apply_to_addons=True,
        benefit_ignore_voucher_discounted=False):
    assert d.subevent_mode == subevent_mode
    assert d.condition_all_products == condition_all_products
    assert [str(p.name) for p in d.condition_limit_products.all()] == condition_limit_products
    assert d.condition_apply_to_addons == condition_apply_to_addons
    assert d.condition_ignore_voucher_discounted == condition_ignore_voucher_discounted
    assert d.condition_min_count == condition_min_count
    assert d.condition_min_value == condition_min_value
    assert d.benefit_same_products == benefit_same_products
    assert [str(p.name) for p in d.benefit_limit_products.all()] == benefit_limit_products
    assert d.benefit_discount_matching_percent == benefit_discount_matching_percent
    assert d.benefit_only_apply_to_cheapest_n_matches == benefit_only_apply_to_cheapest_n_matches
    assert d.benefit_apply_to_addons == benefit_apply_to_addons
    assert d.benefit_ignore_voucher_discounted == benefit_ignore_voucher_discounted
    return d


@scopes_disabled()
@pytest.mark.django_db
def test_rule_parser(event):
    # mixed_min_count_matching_percent
    validate_discount_rule(
        make_discount("Buy at least 3 products, get 20% discount on everything.", event),
        subevent_mode=Discount.SUBEVENT_MODE_MIXED,
        condition_min_count=3,
        benefit_discount_matching_percent=Decimal('20.00')
    )

    # mixed_min_count_one_free
    validate_discount_rule(
        make_discount("For every 3 products, get 100% discount on 1 of them.", event),
        subevent_mode=Discount.SUBEVENT_MODE_MIXED,
        condition_min_count=3,
        benefit_discount_matching_percent=Decimal('100.00'),
        benefit_only_apply_to_cheapest_n_matches=1,
    )

    # mixed_min_value_matching_percent
    validate_discount_rule(
        make_discount("Spend at least 500$, get 20% discount on everything.", event),
        subevent_mode=Discount.SUBEVENT_MODE_MIXED,
        condition_min_value=Decimal('500.00'),
        benefit_discount_matching_percent=Decimal('20.00')
    )

    # same_min_count_matching_percent
    validate_discount_rule(
        make_discount("Buy at least 3 products in the same subevent, get 20% discount on everything.", event),
        subevent_mode=Discount.SUBEVENT_MODE_SAME,
        condition_min_count=3,
        benefit_discount_matching_percent=Decimal('20.00')
    )

    # same_min_count_one_free
    validate_discount_rule(
        make_discount("For every 3 products in the same subevent, get 100% discount on 1 of them.", event),
        subevent_mode=Discount.SUBEVENT_MODE_SAME,
        condition_min_count=3,
        benefit_discount_matching_percent=Decimal('100.00'),
        benefit_only_apply_to_cheapest_n_matches=1,
    )

    # same_min_value_matching_percent
    validate_discount_rule(
        make_discount("Spend at least 500$ in the same subevent, get 20% discount on everything.", event),
        subevent_mode=Discount.SUBEVENT_MODE_SAME,
        condition_min_value=Decimal('500.00'),
        benefit_discount_matching_percent=Decimal('20.00')
    )

    # distinct_min_count_matching_percent
    validate_discount_rule(
        make_discount("Buy at least 3 products in distinct subevents, get 20% discount on everything.", event),
        subevent_mode=Discount.SUBEVENT_MODE_DISTINCT,
        condition_min_count=3,
        benefit_discount_matching_percent=Decimal('20.00')
    )

    # distinct_min_count_one_free
    validate_discount_rule(
        make_discount("For every 3 products in distinct subevents, get 100% discount on 1 of them.", event),
        subevent_mode=Discount.SUBEVENT_MODE_DISTINCT,
        condition_min_count=3,
        benefit_discount_matching_percent=Decimal('100.00'),
        benefit_only_apply_to_cheapest_n_matches=1,
    )

    # distinct_min_count_two_free
    validate_discount_rule(
        make_discount("For every 3 products in distinct subevents, get 100% discount on 2 of them.", event),
        subevent_mode=Discount.SUBEVENT_MODE_DISTINCT,
        condition_min_count=3,
        benefit_discount_matching_percent=Decimal('100.00'),
        benefit_only_apply_to_cheapest_n_matches=2,
    )


def setup_items(event, category_name, category_type, cross_selling_condition, *items):
    cat = event.categories.create(name=category_name)
    cat.category_type = category_type
    cat.cross_selling_condition = cross_selling_condition
    cat.save()
    for name, price in items:
        item = cat.items.create(event=event, name=name, default_price=price)
        quota = event.quotas.create()
        quota.items.add(item)


def split_table(txt):
    return [
        re.split(r"\s{3,}", line.strip())
        for line in txt.split("\n")[1:]
        if line.strip() != ""
    ]


def check_cart_behaviour(event, cart_contents, recommendations):
    cart_contents = split_table(cart_contents)
    positions = [
        CartPosition(
            item_id=event.items.get(name=item_name).pk,
            subevent_id=1, line_price_gross=Decimal(regular_price), addon_to=None, is_bundled=False,
            listed_price=Decimal(regular_price), price_after_voucher=Decimal(regular_price)
        ) for (item_name, regular_price, expected_discounted_price) in cart_contents
    ]
    expected_recommendations = split_table(recommendations)

    service = CrossSellingService(event, event.organizer.sales_channels.get(identifier='web'), positions, None)
    result = service.get_data()
    result_recommendations = [
        [str(category.name), str(item.name), str(item.original_price.gross.quantize(Decimal('0.00'))),
         str(item.display_price.gross.quantize(Decimal('0.00'))), str(item.order_max)]
        for category, items in result
        for item in items
    ]

    assert result_recommendations == expected_recommendations
    assert [str(price) for price, discount in service._discounted_prices] == [
        expected_discounted_price for (item_name, regular_price, expected_discounted_price) in cart_contents]


@scopes_disabled()
@pytest.mark.django_db
def test_2f1r_discount_cross_selling(event):
    setup_items(event, 'Tickets', 'both', 'discounts',
                ('Regular Ticket', '42.00'),
                ('Reduced Ticket', '23.00'),
                )
    make_discount('For every 2 of Regular Ticket, get 50% discount on 1 of Reduced Ticket.', event)

    check_cart_behaviour(
        event,
        cart_contents=''' Price     Discounted
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        ''',
        recommendations='''             Price     Discounted Price    Max Count
        Tickets     Reduced Ticket      23.00                11.50            1
        '''
    )
    check_cart_behaviour(
        event,
        cart_contents=''' Price     Discounted
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00

        Reduced Ticket    23.00          11.50
        ''',
        recommendations='''             Price     Discounted Price    Max Count
        '''
    )
    check_cart_behaviour(
        event,
        cart_contents=''' Price     Discounted
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00

        Reduced Ticket    23.00          11.50
        ''',
        recommendations='''             Price     Discounted Price    Max Count
        '''
    )
    check_cart_behaviour(
        event,
        cart_contents=''' Price     Discounted
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        ''',
        recommendations='''             Price     Discounted Price    Max Count
        Tickets     Reduced Ticket      23.00                11.50            2
        '''
    )
    check_cart_behaviour(
        event,
        cart_contents=''' Price     Discounted
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00

        Reduced Ticket    23.00          11.50
        ''',
        recommendations='''             Price     Discounted Price    Max Count
        Tickets     Reduced Ticket      23.00                11.50            1
        '''
    )
    print("The interesting part:")
    check_cart_behaviour(
        event,
        cart_contents=''' Price     Discounted
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00

        Reduced Ticket    23.00          11.50
        ''',
        recommendations='''             Price     Discounted Price    Max Count
        Tickets     Reduced Ticket      23.00                11.50            1
        '''
    )
    check_cart_behaviour(
        event,
        cart_contents=''' Price     Discounted
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00

        Reduced Ticket    23.00          11.50
        ''',
        recommendations='''             Price     Discounted Price    Max Count
        Tickets     Reduced Ticket      23.00                11.50            2
        '''
    )


@scopes_disabled()
@pytest.mark.django_db
@pytest.mark.skip("currently unsupported (cannot give discount to specific product on minimum cart value)")
def test_free_drinks(event):
    setup_items(event, 'Tickets', 'normal', None,
                ('Regular Ticket', '42.00'),
                ('Reduced Ticket', '23.00'),
                )
    setup_items(event, 'Free Drinks', 'only', 'discounts',
                ('Free Drinks', '50.00'),
                )
    make_discount('Spend at least 100$, get 100% discount on 1 of Free Drinks.', event)

    check_cart_behaviour(
        event,
        cart_contents=''' Price     Discounted
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        ''',
        recommendations='''             Price     Discounted Price    Max Count
        '''
    )
    check_cart_behaviour(
        event,
        cart_contents=''' Price     Discounted
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        ''',
        recommendations='''             Price     Discounted Price    Max Count
        Free Drinks     Free Drinks     50.00                 0.00            1
        '''
    )
    check_cart_behaviour(
        event,
        cart_contents=''' Price     Discounted
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Free Drinks       50.00           0.00
        ''',
        recommendations='''             Price     Discounted Price    Max Count
        '''
    )


@scopes_disabled()
@pytest.mark.django_db
def test_five_tickets_one_free(event):
    setup_items(event, 'Tickets', 'both', 'discounts',
                ('Regular Ticket', '42.00'),
                )
    make_discount('For every 5 of Regular Ticket, get 100% discount on 1 of them.', event)
    # we don't expect a recommendation here, as in the current implementation we only recommend based on discounts
    # where the condition is already completely satisfied but no (or not enough) benefitting products are in the
    # cart yet
    check_cart_behaviour(
        event,
        cart_contents=''' Price     Discounted
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        ''',
        recommendations='''             Price     Discounted Price    Max Count
        '''
    )
    check_cart_behaviour(
        event,
        cart_contents=''' Price     Discounted
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00           0.00
        ''',
        recommendations='''             Price     Discounted Price    Max Count
        '''
    )
    check_cart_behaviour(
        event,
        cart_contents=''' Price     Discounted
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00          42.00
        Regular Ticket    42.00           0.00
        ''',
        recommendations='''             Price     Discounted Price    Max Count
        '''
    )
